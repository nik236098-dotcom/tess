#!/usr/bin/env bash
set -e
F=/opt/beeline/test_beeline.py
echo "=== DEEPSEEK CALL SITES ==="
grep -n -E 'api\.deepseek|chat/completions|messages.*system|role.*system|_agent_system_prompt|read_runtime_console|RUNTIME_CONSOLE' "$F" | head -250
