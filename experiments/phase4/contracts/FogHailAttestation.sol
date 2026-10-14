// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title FogHail 存證＋雙邊信譽合約（v3，2026-10-14）
/// @notice 對照同事外審第 2 題與代理自查的問題，v3 在 v2（防重複結算、雙方簽評分、ΔR 由合約算、
///         鹽值信標）之上再補：
///   (a) 門檻發行：4 個驗證節點各持一把憑證金鑰，憑證要帶其中 T=3 把各自的 Schnorr 盲簽章，
///       合約在結算時逐一驗證（ecrecover 技巧，secp256k1）。
///   (b) 憑證綁假名：憑證簽的訊息就是本趟假名的地址，結算後該假名標為已用（一次性）。
///   (c) 發行前檢查信譽：根身分要 openBatch 才能領憑證；openBatch 要求 R_root ≥ θ 且上一批已清帳。
///       驗證節點只對「已開、未領滿」的批次簽章（鏈下依本合約狀態判定）。
///   (d) 信譽累積：結算後每個假名有一筆待領 ΔR；假名向驗證節點領一張依面額盲簽的收據，
///       根身分 deposit 收據時合約驗章、記序號、把 ΔR 加到 R_root。收據經盲化，無法連回假名。
///   (e) 負評逃避：openBatch(B) 後 outstanding = B，只能靠 deposit 收據或交回未用憑證扣減；
///       outstanding 歸零前不能開新批次。用過的憑證只能用它那一趟的收據抵。
///   (f) 串通捏造行程：結算要附霧節點對 (tripHash, 乘客假名, 駕駛假名) 的媒合簽章。
///   (g) 洗白：根身分只能由 registrar 註冊（一人一個根身分，由平台的身分查核負責）。
contract FogHailAttestation {
    uint256 private constant N =
        0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
    uint8 public constant T = 3;            // 門檻：4 把中要 3 把
    uint8 public constant V = 4;            // 驗證節點數
    uint256 public constant MAX_BATCH = 64;

    struct Key { uint256 px; uint8 parity; }
    struct Sig { uint8 idx; address r; uint256 s; }   // 第 idx 個驗證節點的 (addrR', s')

    Key[4] private credKey;
    Key[4][5] private receiptKey;           // [ΔR + 2][驗證節點]
    mapping(address => bool) public isFog;
    address public immutable registrar;
    int256 public immutable theta;
    uint256 public immutable epochBlocks;

    // 鹽值信標
    mapping(uint256 => bytes32) public epochSalt;
    // 身分表（根身分）
    mapping(address => bool) public registered;
    mapping(address => int256) public rootRep;
    mapping(address => uint256) public outstanding;
    mapping(address => uint256) public batchNonce;
    mapping(address => uint256) public batchSize;
    // 行程與一次性物件
    mapping(bytes32 => bool) public tripExists;
    mapping(address => bool) public pseudonymSpent;   // 憑證 = 假名地址
    mapping(address => bool) public hasPending;       // 假名有待領收據
    mapping(address => int8) public pendingDelta;
    mapping(bytes32 => bool) public receiptSpent;

    event EpochSalt(uint256 indexed epoch, bytes32 salt);
    event RootRegistered(address indexed root);
    event BatchOpened(address indexed root, uint256 nonce, uint256 size);
    event TripAttested(bytes32 indexed tripHash, uint256 timestamp);
    event Settled(address indexed pseudonym, int8 delta);
    event Deposited(address indexed root, uint256 items, int256 newRep);

    constructor(uint256[4] memory credPx, uint8[4] memory credParity,
                uint256[20] memory rcptPx, uint8[20] memory rcptParity,
                address[] memory fogNodes, address _registrar, int256 _theta, uint256 _epochBlocks) {
        require(_epochBlocks > 0, "epochBlocks");
        for (uint256 v = 0; v < V; v++) {
            credKey[v] = Key(credPx[v], credParity[v]);
            for (uint256 d = 0; d < 5; d++) {
                receiptKey[d][v] = Key(rcptPx[d * V + v], rcptParity[d * V + v]);
            }
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
        outstanding[msg.sender] = size;
        batchSize[msg.sender] = size;
        batchNonce[msg.sender] += 1;
        emit BatchOpened(msg.sender, batchNonce[msg.sender], size);
    }

    // ------------------------------------------------------------ 結算
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
        address pseudonym;   // 本趟（乘客）或本班（駕駛）假名，也是憑證的訊息
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
    struct Receipt { bytes32 serial; int8 delta; Sig[3] sigs; }
    struct Unused { address pseudonym; Sig[3] cred; }

    function deposit(Receipt[] calldata rs, Unused[] calldata us) external {
        uint256 items = rs.length + us.length;
        require(items > 0 && items <= outstanding[msg.sender], "items");
        int256 sum = 0;
        for (uint256 i = 0; i < rs.length; i++) {
            Receipt calldata r = rs[i];
            require(r.delta >= -2 && r.delta <= 2, "delta");
            require(!receiptSpent[r.serial], "receipt spent");
            _checkCred(receiptKey[uint256(int256(r.delta) + 2)], abi.encodePacked(r.serial), r.sigs);
            receiptSpent[r.serial] = true;
            sum += r.delta;
        }
        for (uint256 j = 0; j < us.length; j++) {
            Unused calldata u = us[j];
            require(!pseudonymSpent[u.pseudonym], "credential spent");
            _checkCred(credKey, abi.encodePacked(u.pseudonym), u.cred);
            pseudonymSpent[u.pseudonym] = true;
        }
        outstanding[msg.sender] -= items;
        rootRep[msg.sender] += sum;
        emit Deposited(msg.sender, items, rootRep[msg.sender]);
    }

    // ------------------------------------------------------------ 驗章
    function _checkCred(Key[4] storage keys, bytes memory m, Sig[3] calldata sigs) private view {
        uint256 seen = 0;
        for (uint256 i = 0; i < T; i++) {
            uint8 v = sigs[i].idx;
            require(v < V && (seen & (1 << v)) == 0, "signer index");
            seen |= (1 << v);
            require(_schnorr(keys[v], m, sigs[i].r, sigs[i].s), "credential sig");
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
