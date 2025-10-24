#!/bin/bash
# Week 3: Deploy to BSC Testnet
# Deploys FlashArbitrage contract and tests execution

set -e

echo "======================================================================"
echo "  WEEK 3: TESTNET DEPLOYMENT & EXECUTION TEST"
echo "======================================================================"
echo ""

# Check for required tools
if ! command -v node &> /dev/null; then
    echo "❌ Error: Node.js not found. Install from https://nodejs.org/"
    exit 1
fi

# Initialize Hardhat project if needed
if [ ! -f "hardhat.config.js" ]; then
    echo "Setting up Hardhat project..."
    npm init -y
    npm install --save-dev hardhat @nomicfoundation/hardhat-toolbox

    # Create Hardhat config
    cat > hardhat.config.js << 'EOF'
require("@nomicfoundation/hardhat-toolbox");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.19",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      }
    }
  },
  networks: {
    bscTestnet: {
      url: "https://data-seed-prebsc-1-s1.binance.org:8545",
      chainId: 97,
      accounts: process.env.DEX_PRIVATE_KEY ? [process.env.DEX_PRIVATE_KEY] : []
    },
    bsc: {
      url: "https://bsc-dataseed.binance.org",
      chainId: 56,
      accounts: process.env.DEX_PRIVATE_KEY ? [process.env.DEX_PRIVATE_KEY] : []
    }
  },
  etherscan: {
    apiKey: {
      bscTestnet: process.env.BSCSCAN_API_KEY || "",
      bsc: process.env.BSCSCAN_API_KEY || ""
    }
  }
};
EOF

    echo "✓ Hardhat project initialized"
fi

# Create deployment script
mkdir -p scripts
cat > scripts/deploy-flash-arb.js << 'EOF'
const hre = require("hardhat");

async function main() {
  console.log("Deploying FlashArbitrage contract...");

  const FlashArbitrage = await hre.ethers.getContractFactory("FlashArbitrage");
  const flashArb = await FlashArbitrage.deploy();

  await flashArb.waitForDeployment();
  const address = await flashArb.getAddress();

  console.log("✓ FlashArbitrage deployed to:", address);
  console.log("");
  console.log("Next steps:");
  console.log("1. Fund contract with testnet tokens");
  console.log("2. Verify contract on BSCScan:");
  console.log(`   npx hardhat verify --network bscTestnet ${address}`);
  console.log("");
  console.log("3. Update Python config with contract address:");
  console.log(`   router_address = "${address}"`);

  return address;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
EOF

echo ""
echo "Prerequisites Check:"
echo "────────────────────────────────────────────────────────────────"
echo ""

# Check for private key
if [ -z "$DEX_PRIVATE_KEY" ]; then
    echo "⚠️  Warning: DEX_PRIVATE_KEY not set"
    echo ""
    echo "To deploy, you need:"
    echo "1. Create a new wallet for testing"
    echo "2. Export private key:"
    echo "   export DEX_PRIVATE_KEY='0x...'"
    echo "3. Get testnet BNB from faucet:"
    echo "   https://testnet.binance.org/faucet-smart"
    echo ""
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✓ Private key configured"
fi

echo ""
echo "────────────────────────────────────────────────────────────────"
echo "  DEPLOYMENT OPTIONS"
echo "────────────────────────────────────────────────────────────────"
echo ""
echo "1. Compile contract only"
echo "2. Deploy to BSC Testnet"
echo "3. Verify on BSCScan"
echo "4. Run testnet execution test"
echo "5. Full setup (compile + deploy + test)"
echo ""
read -p "Select option (1-5): " option

case $option in
    1)
        echo ""
        echo "Compiling contract..."
        npx hardhat compile
        echo ""
        echo "✓ Contract compiled successfully"
        echo "  Output: artifacts/contracts/FlashArbitrage.sol/FlashArbitrage.json"
        ;;

    2)
        if [ -z "$DEX_PRIVATE_KEY" ]; then
            echo "❌ Error: DEX_PRIVATE_KEY required for deployment"
            exit 1
        fi

        echo ""
        echo "Compiling and deploying to BSC Testnet..."
        npx hardhat compile
        npx hardhat run scripts/deploy-flash-arb.js --network bscTestnet
        ;;

    3)
        if [ -z "$BSCSCAN_API_KEY" ]; then
            echo "⚠️  Warning: BSCSCAN_API_KEY not set (optional)"
            echo "Get API key from: https://bscscan.com/myapikey"
        fi

        read -p "Enter contract address to verify: " CONTRACT_ADDR
        echo ""
        echo "Verifying contract..."
        npx hardhat verify --network bscTestnet "$CONTRACT_ADDR"
        ;;

    4)
        if [ -z "$DEX_PRIVATE_KEY" ]; then
            echo "❌ Error: DEX_PRIVATE_KEY required for testing"
            exit 1
        fi

        read -p "Enter deployed contract address: " CONTRACT_ADDR

        # Create testnet config
        cat > configs/dex_bsc_testnet.yaml << TESTNET_EOF
# BSC Testnet Configuration
rpc_url: "https://data-seed-prebsc-1-s1.binance.org:8545"
poll_sec: 5
once: false

# Testing parameters (conservative)
usd_token: "USDT"
max_position_usd: 10  # Small test trades
slippage_bps: 30
threshold_net_pct: 0.5  # Higher threshold for safety

# Dynamic slippage
use_dynamic_slippage: true
slippage_safety_multiplier: 1.5  # Higher safety on testnet

# Pool quality
enable_pool_quality_filter: true
min_pool_quality_score: 60.0  # Higher quality for testing

# Gas (testnet)
gas_price_gwei: 10.0
gas_limit: 300000
gas_cost_usd_override: 0.02

# Testnet tokens (BSC Testnet)
tokens:
  USDT:
    address: "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd"  # Testnet USDT
    decimals: 18
  WBNB:
    address: "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"  # Testnet WBNB
    decimals: 18

# Dynamic pools (testnet has fewer)
dynamic_pools:
  enabled: true
  min_liquidity_usd: 1000
  max_pools_per_dex: 50
  max_scan_pools: 200
  factories:
    - name: "pancakeswap_testnet"
      address: "0x6725F303b657a9451d8BA641348b6761A6CC7a17"
      fee_bps: 25

dexes: []
TESTNET_EOF

        echo ""
        echo "Running testnet execution test..."
        echo "Contract: $CONTRACT_ADDR"
        echo ""

        python3 run_dex_with_execution.py \
            --config configs/dex_bsc_testnet.yaml \
            --live \
            --min-profit 1.0 \
            --max-gas 20.0
        ;;

    5)
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "  FULL TESTNET SETUP"
        echo "═══════════════════════════════════════════════════════════════"

        # Compile
        echo ""
        echo "Step 1/3: Compiling contract..."
        npx hardhat compile
        echo "✓ Compilation complete"

        # Deploy
        if [ -z "$DEX_PRIVATE_KEY" ]; then
            echo ""
            echo "❌ Cannot deploy without DEX_PRIVATE_KEY"
            echo ""
            echo "Please:"
            echo "1. Get testnet BNB: https://testnet.binance.org/faucet-smart"
            echo "2. Set private key: export DEX_PRIVATE_KEY='0x...'"
            echo "3. Run this script again"
            exit 1
        fi

        echo ""
        echo "Step 2/3: Deploying to testnet..."
        CONTRACT_ADDR=$(npx hardhat run scripts/deploy-flash-arb.js --network bscTestnet | grep "deployed to:" | awk '{print $4}')

        if [ -z "$CONTRACT_ADDR" ]; then
            echo "❌ Deployment failed"
            exit 1
        fi

        echo "✓ Deployed to: $CONTRACT_ADDR"

        # Save contract address
        echo "$CONTRACT_ADDR" > .contract_address_testnet

        echo ""
        echo "Step 3/3: Creating testnet config..."

        # Create testnet config with contract address
        cat > configs/dex_bsc_testnet.yaml << TESTNET_EOF
# BSC Testnet - Deployed Contract: $CONTRACT_ADDR
rpc_url: "https://data-seed-prebsc-1-s1.binance.org:8545"
poll_sec: 5
once: false

usd_token: "USDT"
max_position_usd: 10
slippage_bps: 30
threshold_net_pct: 0.5

use_dynamic_slippage: true
slippage_safety_multiplier: 1.5

enable_pool_quality_filter: true
min_pool_quality_score: 60.0

gas_price_gwei: 10.0
gas_limit: 300000
gas_cost_usd_override: 0.02

tokens:
  USDT:
    address: "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd"
    decimals: 18
  WBNB:
    address: "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"
    decimals: 18

dynamic_pools:
  enabled: true
  min_liquidity_usd: 1000
  max_pools_per_dex: 50
  max_scan_pools: 200
  factories:
    - name: "pancakeswap_testnet"
      address: "0x6725F303b657a9451d8BA641348b6761A6CC7a17"
      fee_bps: 25

dexes: []
TESTNET_EOF

        echo "✓ Config created: configs/dex_bsc_testnet.yaml"
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "  ✓ TESTNET SETUP COMPLETE"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "Contract deployed to: $CONTRACT_ADDR"
        echo "View on explorer: https://testnet.bscscan.com/address/$CONTRACT_ADDR"
        echo ""
        echo "Next steps:"
        echo "1. Fund contract with testnet USDT"
        echo "2. Run execution test:"
        echo "   python3 run_dex_with_execution.py --config configs/dex_bsc_testnet.yaml --live"
        echo ""
        ;;

    *)
        echo "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  DONE"
echo "════════════════════════════════════════════════════════════════"
