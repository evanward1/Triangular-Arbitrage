#!/bin/bash
python run_clean.py 1 &
PID=$!
sleep 300
kill $PID 2>/dev/null
wait $PID 2>/dev/null
