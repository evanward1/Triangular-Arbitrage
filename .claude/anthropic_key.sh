#!/bin/sh
# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi
echo "$ANTHROPIC_API_KEY"
