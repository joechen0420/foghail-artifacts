// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title FogHail 存證＋雙邊信譽合約
/// @notice 鏈上僅存行程指紋與假名信譽；明細密文留本地（雙層儲存）。
///         發行/更新由許可鏈驗證者（QBFT）執行，取代 PrivateRide 的中心化 SP。
contract FogHailAttestation {
    // 假名 -> 信譽值（乘客與駕駛共用；假名每行程/班次輪換）
    mapping(bytes32 => int256) public reputation;
    // 行程指紋存在性（防重放/重複結算）
    mapping(bytes32 => bool) public tripExists;

    event TripAttested(bytes32 indexed tripHash, uint256 timestamp);
    event ReputationUpdated(bytes32 indexed pseudonym, int256 newValue);

    /// @notice 存證：鏈上僅寫入 {TripHash, timestamp}
    function attestTrip(bytes32 tripHash) external {
        require(!tripExists[tripHash], "trip exists");
        tripExists[tripHash] = true;
        emit TripAttested(tripHash, block.timestamp);
    }

    /// @notice 雙邊互評更新：與行程存證原子綁定（必須先有 tripHash）
    /// @param tripHash 對應行程指紋
    /// @param riderPseudo 乘客本次假名
    /// @param driverPseudo 駕駛本班次假名
    /// @param dRider 乘客信譽增量 ΔR(status, rating)
    /// @param dDriver 駕駛信譽增量
    function settleTrip(
        bytes32 tripHash,
        bytes32 riderPseudo,
        bytes32 driverPseudo,
        int256 dRider,
        int256 dDriver
    ) external {
        require(tripExists[tripHash], "no such trip");
        reputation[riderPseudo] += dRider;
        reputation[driverPseudo] += dDriver;
        emit ReputationUpdated(riderPseudo, reputation[riderPseudo]);
        emit ReputationUpdated(driverPseudo, reputation[driverPseudo]);
    }

    /// @notice 存證＋結算合併（一筆交易），量測用
    function attestAndSettle(
        bytes32 tripHash,
        bytes32 riderPseudo,
        bytes32 driverPseudo,
        int256 dRider,
        int256 dDriver
    ) external {
        require(!tripExists[tripHash], "trip exists");
        tripExists[tripHash] = true;
        reputation[riderPseudo] += dRider;
        reputation[driverPseudo] += dDriver;
        emit TripAttested(tripHash, block.timestamp);
        emit ReputationUpdated(riderPseudo, reputation[riderPseudo]);
        emit ReputationUpdated(driverPseudo, reputation[driverPseudo]);
    }
}
