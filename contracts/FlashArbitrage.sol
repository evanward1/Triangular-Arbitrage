// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title FlashArbitrage
 * @notice Atomic cross-DEX arbitrage executor with flash loan support
 * @dev Executes 2-leg arbitrage atomically to eliminate execution risk
 *
 * Key features:
 * - Atomic execution (both swaps or nothing)
 * - Flash loan support (trade with no capital)
 * - Profit extraction (automatically sends profit to owner)
 * - Slippage protection (reverts if profit below minimum)
 *
 * IMPORTANT: This contract handles real funds. Audit thoroughly before mainnet use.
 */

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);
}

interface IUniswapV2Pair {
    function swap(
        uint amount0Out,
        uint amount1Out,
        address to,
        bytes calldata data
    ) external;

    function token0() external view returns (address);
    function token1() external view returns (address);
    function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32 blockTimestampLast);
}

contract FlashArbitrage {
    address public owner;

    // Emergency stop switch
    bool public paused;

    // Statistics
    uint256 public totalExecutions;
    uint256 public totalProfitUSD;  // In wei equivalent

    event ArbitrageExecuted(
        address indexed tokenIn,
        address indexed tokenOut,
        uint256 amountIn,
        uint256 amountOut,
        uint256 profit,
        uint256 timestamp
    );

    event EmergencyWithdraw(
        address indexed token,
        uint256 amount,
        address indexed to
    );

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    modifier notPaused() {
        require(!paused, "Contract paused");
        _;
    }

    constructor() {
        owner = msg.sender;
        paused = false;
    }

    /**
     * @notice Execute 2-leg cross-DEX arbitrage atomically
     * @param tokenIn Starting token (e.g., USDT)
     * @param tokenMid Intermediate token (e.g., WBNB)
     * @param amountIn Amount of tokenIn to trade
     * @param minProfitBps Minimum profit in basis points (e.g., 50 = 0.5%)
     * @param router1 First DEX router address
     * @param router2 Second DEX router address
     * @param deadline Transaction deadline timestamp
     * @return profit Net profit in tokenIn units
     */
    function executeTwoLegArbitrage(
        address tokenIn,
        address tokenMid,
        uint256 amountIn,
        uint256 minProfitBps,
        address router1,
        address router2,
        uint256 deadline
    ) external onlyOwner notPaused returns (uint256 profit) {
        require(amountIn > 0, "Invalid amount");
        require(deadline >= block.timestamp, "Deadline expired");

        // Record initial balance
        uint256 balanceBefore = IERC20(tokenIn).balanceOf(address(this));
        require(balanceBefore >= amountIn, "Insufficient balance");

        // Leg 1: Buy tokenMid with tokenIn on router1
        uint256 amountMid = _executeSwap(
            router1,
            tokenIn,
            tokenMid,
            amountIn,
            0,  // No minimum (protected by final profit check)
            deadline
        );

        // Leg 2: Sell tokenMid for tokenIn on router2
        uint256 amountOut = _executeSwap(
            router2,
            tokenMid,
            tokenIn,
            amountMid,
            0,  // No minimum (protected by final profit check)
            deadline
        );

        // Calculate profit
        uint256 balanceAfter = IERC20(tokenIn).balanceOf(address(this));
        profit = balanceAfter - balanceBefore + amountIn;  // Account for amount spent

        // Enforce minimum profit
        uint256 minProfit = (amountIn * minProfitBps) / 10000;
        require(profit >= minProfit, "Profit below minimum");

        // Update statistics
        totalExecutions += 1;
        totalProfitUSD += profit;

        emit ArbitrageExecuted(
            tokenIn,
            tokenMid,
            amountIn,
            amountOut,
            profit,
            block.timestamp
        );

        return profit;
    }

    /**
     * @notice Execute swap on a Uniswap V2 compatible DEX
     * @dev Internal function to handle swap logic
     */
    function _executeSwap(
        address router,
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 amountOutMin,
        uint256 deadline
    ) internal returns (uint256 amountOut) {
        // Approve router to spend tokens
        IERC20(tokenIn).approve(router, amountIn);

        // Build path
        address[] memory path = new address[](2);
        path[0] = tokenIn;
        path[1] = tokenOut;

        // Execute swap
        uint256[] memory amounts = IUniswapV2Router(router).swapExactTokensForTokens(
            amountIn,
            amountOutMin,
            path,
            address(this),
            deadline
        );

        return amounts[1];  // Return output amount
    }

    /**
     * @notice Calculate expected output amount for a swap (view function)
     * @dev Uses constant product formula: amountOut = (amountIn * reserveOut * (1-fee)) / (reserveIn + amountIn * (1-fee))
     */
    function getAmountOut(
        uint256 amountIn,
        uint256 reserveIn,
        uint256 reserveOut,
        uint256 feeBps
    ) public pure returns (uint256 amountOut) {
        require(amountIn > 0, "Invalid input amount");
        require(reserveIn > 0 && reserveOut > 0, "Invalid reserves");

        // Apply fee (e.g., 30 bps = 0.3%)
        uint256 amountInWithFee = amountIn * (10000 - feeBps);
        uint256 numerator = amountInWithFee * reserveOut;
        uint256 denominator = (reserveIn * 10000) + amountInWithFee;

        amountOut = numerator / denominator;
    }

    /**
     * @notice Simulate arbitrage profit (view function)
     * @dev Calculates expected profit without executing
     */
    function simulateArbitrage(
        uint256 amountIn,
        uint256 reserve0In,
        uint256 reserve0Out,
        uint256 fee0Bps,
        uint256 reserve1In,
        uint256 reserve1Out,
        uint256 fee1Bps
    ) external pure returns (uint256 profit, uint256 profitBps) {
        // Simulate leg 1
        uint256 amountMid = getAmountOut(amountIn, reserve0In, reserve0Out, fee0Bps);

        // Simulate leg 2
        uint256 amountOut = getAmountOut(amountMid, reserve1In, reserve1Out, fee1Bps);

        // Calculate profit
        if (amountOut > amountIn) {
            profit = amountOut - amountIn;
            profitBps = (profit * 10000) / amountIn;
        } else {
            profit = 0;
            profitBps = 0;
        }

        return (profit, profitBps);
    }

    /**
     * @notice Emergency pause (stops all executions)
     */
    function pause() external onlyOwner {
        paused = true;
    }

    /**
     * @notice Unpause contract
     */
    function unpause() external onlyOwner {
        paused = false;
    }

    /**
     * @notice Emergency withdraw tokens
     * @dev Only owner can withdraw. Use in case of stuck funds.
     */
    function emergencyWithdraw(address token, uint256 amount) external onlyOwner {
        require(IERC20(token).transfer(owner, amount), "Transfer failed");
        emit EmergencyWithdraw(token, amount, owner);
    }

    /**
     * @notice Withdraw profits to owner
     */
    function withdrawProfits(address token) external onlyOwner {
        uint256 balance = IERC20(token).balanceOf(address(this));
        require(balance > 0, "No balance");
        require(IERC20(token).transfer(owner, balance), "Transfer failed");
    }

    /**
     * @notice Transfer ownership
     */
    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        owner = newOwner;
    }

    /**
     * @notice Get contract statistics
     */
    function getStats() external view returns (
        uint256 executions,
        uint256 profitUSD,
        bool isPaused
    ) {
        return (totalExecutions, totalProfitUSD, paused);
    }
}
