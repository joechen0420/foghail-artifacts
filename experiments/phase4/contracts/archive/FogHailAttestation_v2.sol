// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title FogHail 存證＋雙邊信譽合約（v2，2026-10-14）
/// @notice 鏈上僅存行程指紋、已用憑證序號、假名信譽與每期鹽值；明細密文留本地（雙層儲存）。
///         v2 依同事外審第 2 題補上：
///         (1) 結算只有一個入口 attestAndSettle，同一 tripHash 只能結算一次（原 settleTrip 可重複呼叫，已移除）；
///         (2) 兩方各自用本趟假名私鑰簽「自己給對方的評分」，合約以 ecrecover 驗證，提交者（霧節點）無法代填或竄改；
///         (3) 兩方各出示一張一次性憑證的序號，合約記錄為已用，同一張憑證不能用第二次；
///         (4) ΔR 由合約依 (status, rating) 計算，不再由呼叫者傳入；
///         (5) 鹽值信標：每個 epoch 第一次呼叫 rollEpoch() 時，以前一個區塊的 hash 產生該期鹽值。
///         憑證本身（Schnorr 盲簽章）的有效性由對方在行程前於鏈下驗證（Table 7），合約只負責防止重複使用。
contract FogHailAttestation {
    uint256 public immutable epochBlocks;

    mapping(uint256 => bytes32) public epochSalt;     // epoch -> 鹽值
    mapping(address => int256) public reputation;      // 假名 -> 信譽
    mapping(bytes32 => bool) public tripExists;        // 行程指紋（防重複結算）
    mapping(bytes32 => bool) public credentialSpent;   // 一次性憑證序號（防重複使用）

    event EpochSalt(uint256 indexed epoch, bytes32 salt);
    event TripAttested(bytes32 indexed tripHash, uint256 timestamp);
    event ReputationUpdated(address indexed pseudonym, int256 newValue);

    constructor(uint256 _epochBlocks) {
        require(_epochBlocks > 0, "epochBlocks");
        epochBlocks = _epochBlocks;
    }

    function currentEpoch() public view returns (uint256) {
        return block.number / epochBlocks;
    }

    /// @notice 鹽值信標：任何人皆可呼叫，每期只能設定一次。
    function rollEpoch() external returns (bytes32 s) {
        uint256 e = currentEpoch();
        require(epochSalt[e] == bytes32(0), "salt set");
        s = keccak256(abi.encode(blockhash(block.number - 1), e));
        epochSalt[e] = s;
        emit EpochSalt(e, s);
    }

    /// @notice ΔR(status, rating)：完成的行程 rating 1–5 對應 −2…+2；取消或未到 −2。
    function ratingDelta(uint8 status, uint8 rating) public pure returns (int256) {
        require(rating >= 1 && rating <= 5, "rating");
        if (status != 0) return -2;
        return int256(uint256(rating)) - 3;
    }

    /// @notice 一方要簽的內容：本合約、本鏈、行程、狀態、給對方的評分、對方假名、自己出示的憑證序號。
    function ratingDigest(bytes32 tripHash, uint8 status, uint8 rating,
                          address counterpart, bytes32 credSerial) public view returns (bytes32) {
        return keccak256(abi.encode(address(this), block.chainid, tripHash, status,
                                    rating, counterpart, credSerial));
    }

    struct Party {
        address pseudonym;   // 本趟（乘客）或本班（駕駛）假名
        uint8 gives;         // 給對方的評分
        bytes32 credSerial;  // 出示的一次性憑證序號
        bytes sig;           // 對 ratingDigest 的 EIP-191 簽章（65 B）
    }

    /// @notice 存證＋雙邊結算，一筆交易、只能一次。
    function attestAndSettle(bytes32 tripHash, uint8 status,
                             Party calldata rider, Party calldata driver) external {
        require(!tripExists[tripHash], "trip exists");
        require(rider.credSerial != driver.credSerial, "same credential");
        require(!credentialSpent[rider.credSerial] && !credentialSpent[driver.credSerial],
                "credential spent");
        require(_signer(ratingDigest(tripHash, status, rider.gives, driver.pseudonym,
                                     rider.credSerial), rider.sig) == rider.pseudonym, "rider sig");
        require(_signer(ratingDigest(tripHash, status, driver.gives, rider.pseudonym,
                                     driver.credSerial), driver.sig) == driver.pseudonym, "driver sig");

        tripExists[tripHash] = true;
        credentialSpent[rider.credSerial] = true;
        credentialSpent[driver.credSerial] = true;
        reputation[driver.pseudonym] += ratingDelta(status, rider.gives);
        reputation[rider.pseudonym] += ratingDelta(status, driver.gives);

        emit TripAttested(tripHash, block.timestamp);
        emit ReputationUpdated(driver.pseudonym, reputation[driver.pseudonym]);
        emit ReputationUpdated(rider.pseudonym, reputation[rider.pseudonym]);
    }

    function _signer(bytes32 digest, bytes calldata sig) private pure returns (address) {
        require(sig.length == 65, "sig len");
        bytes32 r = bytes32(sig[0:32]);
        bytes32 s = bytes32(sig[32:64]);
        uint8 v = uint8(sig[64]);
        // 拒絕可塑簽章（EIP-2）
        require(uint256(s) <= 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0, "sig s");
        bytes32 h = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
        address a = ecrecover(h, v, r, s);
        require(a != address(0), "sig");
        return a;
    }
}
