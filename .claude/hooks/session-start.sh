#!/bin/bash
# Installs the Claude Code plugins enabled in .claude/settings.json so they
# are actually available in Claude Code cloud sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Add the impeccable marketplace if it isn't configured yet.
if ! claude plugin marketplace list 2>/dev/null | grep -q '\bimpeccable\b'; then
  claude plugin marketplace add pbakaus/impeccable
fi

install_plugin() {
  local plugin="$1"
  if claude plugin list 2>/dev/null | grep -q "$plugin"; then
    echo "Plugin $plugin already installed"
  else
    claude plugin install "$plugin" --scope user
  fi
}

install_plugin frontend-design@anthropic-plugin-directory
install_plugin impeccable@impeccable
