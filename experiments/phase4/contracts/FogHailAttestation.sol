// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title FogHail 存證＋雙邊信譽合約（v4，2026-10-14）
/// @notice v3 見 contracts/archive/FogHailAttestation_v3.sol。v4 依 外審回稿/Code_Audit_2026-10-14.md 修正：
///   P0-1 配額混用：v3 由各驗證節點自己限簽 B 次，4 個節點可湊出 4B/3 張 3-of-4 憑證。
///        v4 由合約記帳：openBatch(B) 給整批 T·B 個部分簽章的預算，驗證節點每回一個部分簽章前都要
///        logIssue 上鏈，超過預算即拒。每張憑證要 T 個，所以不論怎麼混用節點子集合最多 B 張。
///        outstanding 改以「部分簽章」為單位：收據抵 T、未用憑證抵它帶的部分簽章數（1–4）。
///   P0-2 持有人授權：logIssue 要附根身分對 authDigest(KIND_CRED, 批次號, 節點, h) 的簽章；
///        logReceipt 要附假名對 authDigest(KIND_RCPT, 0, 節點, h) 的簽章；h = keccak(R, e) 綁一次盲簽會談。
///   P0-3 持久化：發行記錄在鏈上，每個假名最多 T 個收據部分簽章（每節點一個），重啟或多實例共用同一份帳。
///   P1  收據移轉：收據序號 = keccak(根身分 ‖ r)，deposit 用 msg.sender 重算；交回未用憑證要附假名的持有證明。
/// 結算 attestAndSettle 與 v3 相同（論文 Table 8 量的就是這一段）。
contract FogHailAttestation {
    uint256 private constant N =
        0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
    uint8 public constant T = 3;            // 門檻：4 把中要 3 把
    uint8 public constant V = 4;            // 驗證節點數
    uint256 public constant MAX_BATCH = 64;
    bytes32 public constant KIND_CRED = keccak256("FOGHAIL_CRED");
    bytes32 public constant KIND_RCPT = keccak256("FOGHAIL_RCPT");
    bytes32 public constant KIND_RETURN = keccak256("FOGHAIL_RETURN");

    struct Key { uint256 px; uint8 parity; }
    struct Sig { uint8 idx; address r; uint256 s; }   // 第 idx 個驗證節點的 (addrR', s')

    Key[4] private credKey;
    Key[4][5] private receiptKey;           // [ΔR + 2][驗證節點]
    address[4] public validatorAddr;        // 驗證節點上鏈記帳用的帳戶
    mapping(address => bool) public isFog;
    address public immutable registrar;
    int256 public immutable theta;
    uint256 public immutable epochBlocks;

    // 鹽值信標
    mapping(uint256 => bytes32) public epochSalt;
    // 身分表（根身分）
    mapping(address => bool) public registered;
    mapping(address => int256) public rootRep;
    mapping(address => uint256) public outstanding;     // 單位：部分簽章
    mapping(address => uint256) public batchNonce;
    mapping(address => uint256) public batchBudget;     // T · B
    mapping(address => uint256) public batchIssued;
    mapping(bytes32 => bool) public sessionLogged;      // h = keccak(R, e)
    // 行程與一次性物件
    mapping(bytes32 => bool) public tripExists;
    mapping(address => bool) public pseudonymSpent;     // 憑證 = 假名地址
    mapping(address => bool) public hasPending;         // 假名有待領收據
    mapping(address => int8) public pendingDelta;
    mapping(address => uint8) public receiptMask;       // 已對此假名發過收據部分簽章的節點
    mapping(bytes32 => bool) public receiptSpent;

    event EpochSalt(uint256 indexed epoch, bytes32 salt);
    event RootRegistered(address indexed root);
    event BatchOpened(address indexed root, uint256 nonce, uint256 size);
    event IssueLogged(address indexed root, uint8 validator);
    event ReceiptLogged(address indexed pseudonym, uint8 validator);
    event TripAttested(bytes32 indexed tripHash, uint256 timestamp);
    event Settled(address indexed pseudonym, int8 delta);
    event Deposited(address indexed root, uint256 units, int256 newRep);

    constructor(uint256[4] memory credPx, uint8[4] memory credParity,
                uint256[20] memory rcptPx, uint8[20] memory rcptParity, address[4] memory validators,
                address[] memory fogNodes, address _registrar, int256 _theta, uint256 _epochBlocks) {
        require(_epochBlocks > 0, "epochBlocks");
        for (uint256 v = 0; v < V; v++) {
            credKey[v] = Key(credPx[v], credParity[v]);
            for (uint256 d = 0; d < 5; d++) {
                receiptKey[d][v] = Key(rcptPx[d * V + v], rcptParity[d * V + v]);
            }
            require(validators[v] != address(0), "validator");
            validatorAddr[v] = validators[v];
        }
        for (uint256 i = 0; i < fogNodes.length; i++) isFog[fogNodes[i]] = true;
        registrar = _registrar;
        theta = _theta;
        epochBlocks = _epochBlocks;
    }

    // ------------------------------------------------------------ 鹽值信標
    function currentEpoch() public view returns (uint256) { return block.number / epochBlocks; }

    function rollEpoch() external returns (bytes32 s) {
        uint256 e = currentEpoch();
        require(epochSalt[e] == bytes32(0), "salt set");
        s = keccak256(abi.encode(blockhash(block.number - 1), e));
        epochSalt[e] = s;
        emit EpochSalt(e, s);
    }

    // ------------------------------------------------------------ 身分與批次
    function registerRoot(address root) external {
        require(msg.sender == registrar, "registrar only");
        require(!registered[root], "registered");
        registered[root] = true;
        emit RootRegistered(root);
    }

    function openBatch(uint256 size) external {
        require(registered[msg.sender], "not registered");
        require(outstanding[msg.sender] == 0, "outstanding");
        require(rootRep[msg.sender] >= theta, "reputation below theta");
        require(size > 0 && size <= MAX_BATCH, "size");
        batchNonce[msg.sender] += 1;
        batchBudget[msg.sender] = T * size;
        batchIssued[msg.sender] = 0;
        emit BatchOpened(msg.sender, batchNonce[msg.sender], size);
    }

    // ------------------------------------------------------------ 發行記帳（驗證節點回應盲簽前呼叫）
    function authDigest(bytes32 kind, uint256 ctx, uint8 v, bytes32 h) public view returns (bytes32) {
        return keccak256(abi.encode(address(this), block.chainid, kind, ctx, v, h));
    }

    function logIssue(address root, bytes32 h, bytes calldata auth) external {
        uint8 v = _validatorIndex();
        require(registered[root], "not registered");
        require(batchIssued[root] < batchBudget[root], "batch budget");
        require(!sessionLogged[h], "session logged");
        require(_ecdsa(authDigest(KIND_CRED, batchNonce[root], v, h), auth) == root, "root auth");
        sessionLogged[h] = true;
        batchIssued[root] += 1;
        outstanding[root] += 1;
        emit IssueLogged(root, v);
    }

    function logReceipt(address p, bytes32 h, bytes calldata auth) external {
        uint8 v = _validatorIndex();
        require(hasPending[p], "no settled trip");
        uint8 mask = receiptMask[p];
        require(mask & uint8(1 << v) == 0, "receipt logged");
        require(_popcount(mask) < T, "receipt quota");
        require(!sessionLogged[h], "session logged");
        require(_ecdsa(authDigest(KIND_RCPT, 0, v, h), auth) == p, "pseudonym auth");
        sessionLogged[h] = true;
        receiptMask[p] = mask | uint8(1 << v);
        emit ReceiptLogged(p, v);
    }

    // ------------------------------------------------------------ 結算（與 v3 相同）
    function ratingDelta(uint8 status, uint8 rating) public pure returns (int8) {
        require(rating >= 1 && rating <= 5, "rating");
        if (status != 0) return -2;
        return int8(int256(uint256(rating)) - 3);
    }

    function ratingDigest(bytes32 tripHash, uint8 status, uint8 rating, address counterpart)
        public view returns (bytes32)
    {
        return keccak256(abi.encode(address(this), block.chainid, tripHash, status, rating, counterpart));
    }

    function matchDigest(bytes32 tripHash, address rider, address driver) public view returns (bytes32) {
        return keccak256(abi.encode(address(this), block.chainid, tripHash, rider, driver));
    }

    struct Party {
        address pseudonym;   // 本趟結算假名，也是憑證的訊息
        uint8 gives;         // 給對方的評分 1–5
        Sig[3] cred;         // T 把驗證節點對假名的盲簽章
        bytes sig;           // 假名對 ratingDigest 的簽章
    }

    function attestAndSettle(bytes32 tripHash, uint8 status, Party calldata rider,
                             Party calldata driver, bytes calldata fogSig) external {
        require(!tripExists[tripHash], "trip exists");
        require(rider.pseudonym != driver.pseudonym, "same pseudonym");
        require(!pseudonymSpent[rider.pseudonym] && !pseudonymSpent[driver.pseudonym], "credential spent");
        require(isFog[_ecdsa(matchDigest(tripHash, rider.pseudonym, driver.pseudonym), fogSig)], "fog sig");
        _checkCred(credKey, abi.encodePacked(rider.pseudonym), rider.cred);
        _checkCred(credKey, abi.encodePacked(driver.pseudonym), driver.cred);
        require(_ecdsa(ratingDigest(tripHash, status, rider.gives, driver.pseudonym), rider.sig)
                == rider.pseudonym, "rider sig");
        require(_ecdsa(ratingDigest(tripHash, status, driver.gives, rider.pseudonym), driver.sig)
                == driver.pseudonym, "driver sig");

        tripExists[tripHash] = true;
        pseudonymSpent[rider.pseudonym] = true;
        pseudonymSpent[driver.pseudonym] = true;
        int8 dDriver = ratingDelta(status, rider.gives);
        int8 dRider = ratingDelta(status, driver.gives);
        hasPending[driver.pseudonym] = true; pendingDelta[driver.pseudonym] = dDriver;
        hasPending[rider.pseudonym] = true;  pendingDelta[rider.pseudonym] = dRider;
        emit TripAttested(tripHash, block.timestamp);
        emit Settled(driver.pseudonym, dDriver);
        emit Settled(rider.pseudonym, dRider);
    }

    // ------------------------------------------------------------ 存回根身分
    struct Receipt { bytes32 r; int8 delta; Sig[3] sigs; }          // 序號 = keccak(根 ‖ r)
    struct Unused { address pseudonym; Sig[] sigs; bytes possession; }

    function returnDigest(address root) public view returns (bytes32) {
        return keccak256(abi.encode(address(this), block.chainid, KIND_RETURN, root));
    }

    function deposit(Receipt[] calldata rs, Unused[] calldata us) external {
        uint256 units = 0;
        int256 sum = 0;
        for (uint256 i = 0; i < rs.length; i++) {
            Receipt calldata r = rs[i];
            require(r.delta >= -2 && r.delta <= 2, "delta");
            bytes32 serial = keccak256(abi.encode(msg.sender, r.r));
            require(!receiptSpent[serial], "receipt spent");
            _checkCred(receiptKey[uint256(int256(r.delta) + 2)], abi.encodePacked(serial), r.sigs);
            receiptSpent[serial] = true;
            sum += r.delta;
            units += T;
        }
        bytes32 rd = returnDigest(msg.sender);
        for (uint256 j = 0; j < us.length; j++) {
            Unused calldata u = us[j];
            require(!pseudonymSpent[u.pseudonym], "credential spent");
            require(_ecdsa(rd, u.possession) == u.pseudonym, "possession");
            require(u.sigs.length > 0 && u.sigs.length <= V, "partials");
            _checkPartials(abi.encodePacked(u.pseudonym), u.sigs);
            pseudonymSpent[u.pseudonym] = true;
            units += u.sigs.length;
        }
        require(units > 0 && units <= outstanding[msg.sender], "units");
        outstanding[msg.sender] -= units;
        rootRep[msg.sender] += sum;
        emit Deposited(msg.sender, units, rootRep[msg.sender]);
    }

    // ------------------------------------------------------------ 驗章與輔助
    function _validatorIndex() private view returns (uint8) {
        for (uint8 v = 0; v < V; v++) if (validatorAddr[v] == msg.sender) return v;
        revert("validator only");
    }

    function _popcount(uint8 x) private pure returns (uint8 c) {
        while (x != 0) { c += x & 1; x >>= 1; }
    }

    function _checkCred(Key[4] storage keys, bytes memory m, Sig[3] calldata sigs) private view {
        uint256 seen = 0;
        for (uint256 i = 0; i < T; i++) {
            uint8 v = sigs[i].idx;
            require(v < V && (seen & (1 << v)) == 0, "signer index");
            seen |= (1 << v);
            require(_schnorr(keys[v], m, sigs[i].r, sigs[i].s), "credential sig");
        }
    }

    function _checkPartials(bytes memory m, Sig[] calldata sigs) private view {
        uint256 seen = 0;
        for (uint256 i = 0; i < sigs.length; i++) {
            uint8 v = sigs[i].idx;
            require(v < V && (seen & (1 << v)) == 0, "signer index");
            seen |= (1 << v);
            require(_schnorr(credKey[v], m, sigs[i].r, sigs[i].s), "credential sig");
        }
    }

    /// Schnorr 驗證：s·G − e·P 的地址 == r，e = keccak(r ‖ m)。用 ecrecover 算 s·G − e·P：
    /// ecrecover(h = −s·Px, v = 27 + parity(P), r = Px, s = −e·Px) = addr(Px⁻¹(−e·Px·P + s·Px·G))。
    function _schnorr(Key storage k, bytes memory m, address r, uint256 s) private view returns (bool) {
        if (r == address(0) || s == 0 || s >= N) return false;
        uint256 e = uint256(keccak256(abi.encodePacked(r, m))) % N;
        bytes32 h = bytes32((N - mulmod(s, k.px, N)) % N);
        bytes32 sv = bytes32((N - mulmod(e, k.px, N)) % N);
        return ecrecover(h, 27 + k.parity, bytes32(k.px), sv) == r;
    }

    function _ecdsa(bytes32 digest, bytes calldata sig) private pure returns (address) {
        require(sig.length == 65, "sig len");
        bytes32 r = bytes32(sig[0:32]);
        bytes32 s = bytes32(sig[32:64]);
        uint8 v = uint8(sig[64]);
        require(uint256(s) <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0, "sig s");
        address a = ecrecover(keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest)), v, r, s);
        require(a != address(0), "sig");
        return a;
    }
}
