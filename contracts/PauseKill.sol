// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Pause & Kill switch for MEV-OG
contract PauseKill {
    address public owner;
    bool public paused;
    bool public killed;

    event Paused(address indexed by);
    event Unpaused(address indexed by);
    event Killed(address indexed by);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier notKilled() {
        require(!killed, "killed");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "paused");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /// @notice Pause the contract
    function pause() external onlyOwner notKilled {
        paused = true;
        emit Paused(msg.sender);
    }

    /// @notice Resume from pause
    function unpause() external onlyOwner notKilled {
        paused = false;
        emit Unpaused(msg.sender);
    }

    /// @notice Kill switch disables all actions permanently
    function kill() external onlyOwner {
        killed = true;
        emit Killed(msg.sender);
    }
}
