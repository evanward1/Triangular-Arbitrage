**Project Canvas: Triangular Arbitrage Bot**
============================================

### **1\. Problem**

-   Finding profitable arbitrage opportunities in cryptocurrency markets is **computationally intensive** and time-consuming.

-   Executing trades manually is too slow to capitalize on fleeting opportunities.

-   Automated trading is risky and prone to errors from **insufficient funds**, or failing to meet exchange-specific rules like **minimum order size** and **minimum order value**.

### **2\. Solution**

A command-line Python application that:

-   **Scans** for profitable, multi-leg arbitrage opportunities on a given exchange.

-   Provides an **"actionable" mode** (`--actionable`) to find trades that can be executed immediately with the user's available funds.

-   Includes a crucial **"dry run" mode** (`--dry-run`) that simulates the entire trade execution process without using real funds, ensuring complete safety during testing.

-   Includes a comprehensive **wallet management** feature (`--wallet`) to display balances and public deposit addresses.

-   Prompts for **interactive trade execution** with robust pre-flight checks to prevent common transaction failures.

### **3\. Key Metrics**

-   Number of profitable opportunities identified.

-   Number of trades successfully executed.

-   Net profit generated over time.

-   Frequency of successful runs without execution errors.

### **4\. Unique Value Proposition**

This tool doesn't just find theoretical opportunities; it provides **actionable, real-time trading suggestions** tailored to your wallet. The built-in pre-trade validation, interactive confirmation, and especially the `--dry-run` simulation provide a crucial **safety layer**, making it a more intelligent and reliable tool than a simple scanner.

### **5\. Unfair Advantage**

The combination of an efficient cycle detection algorithm (`networkx.find_negative_cycle`) with user-specific, actionable intelligence (`--actionable` mode) allows the bot to quickly filter out noise and present only the most relevant trading opportunities.

### **6\. Channels**

-   **Direct Use**: As a personal trading and market analysis tool.

-   **Open Source**: Hosted on GitHub (`Drakkar-Software/Triangular-Arbitrage`) for community collaboration and use.

### **7\. Target Users**

-   Algorithmic traders looking for a reliable arbitrage detection engine.

-   Manual crypto traders who want to automate the discovery phase of their strategy.

-   Python developers interested in cryptocurrency trading and API integration.

### **8\. Usage**

**Prerequisites:**

1.  Ensure all dependencies are installed: `pip install -r requirements.txt`

2.  Create a `.env` file in the root directory with your exchange API keys:

    ```
    EXCHANGE_API_KEY=your_api_key_here
    EXCHANGE_API_SECRET=your_api_secret_here

    ```

**Commands:**

-   **Check Wallet Balance:**

    ```
    python3 main.py --wallet

    ```

-   **Safe Testing (Dry Run):** Simulate the entire trade execution logic without using real money. This is the recommended way to test.

    -   Simulate a general opportunity scan:

        ```
        python3 main.py --dry-run

        ```

    -   Simulate an actionable scan based on your wallet:

        ```
        python3 main.py --actionable --dry-run

        ```

-   **Live Trading:** Scan for and execute real trades. Only use this after you are confident with the dry run results.

    ```
    python3 main.py --actionable

    ```

### **9\. Cost Structure**

-   **Trading Fees**: Standard exchange fees are incurred on every executed trade.

-   **Development Time**: The primary investment is the time spent building, testing, and refining the script's logic.

### **10\. Revenue Streams**

-   Currently a personal tool with no direct revenue model.

-   Potential future monetization could involve offering it as a hosted service or developing more advanced, proprietary features.