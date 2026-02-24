#!/usr/bin/env bash
#
# find_largest_files.sh - Find the top 50 largest files on the system
#
# Usage:
#   ./find_largest_files.sh [directory]
#
# If no directory is given, defaults to / (entire filesystem).
# Virtual/pseudo filesystems (proc, sys, dev, etc.) are excluded.

set -euo pipefail

search_dir="${1:-/}"

echo "Searching for the 50 largest files under: $search_dir"
echo "This may take a while depending on disk size..."
echo ""

printf "%-12s  %s\n" "SIZE" "FILE"
printf "%s\n" "------------------------------------------------------------"

find "$search_dir" \
    -xdev \
    -path /proc -prune -o \
    -path /sys -prune -o \
    -path /dev -prune -o \
    -path /run -prune -o \
    -path /snap -prune -o \
    -type f -printf '%s %p\n' 2>/dev/null \
  | sort -rn \
  | head -n 50 \
  | while read -r size filepath; do
      if [ "$size" -ge 1073741824 ]; then
        human=$(awk "BEGIN {printf \"%.2f GB\", $size/1073741824}")
      elif [ "$size" -ge 1048576 ]; then
        human=$(awk "BEGIN {printf \"%.2f MB\", $size/1048576}")
      elif [ "$size" -ge 1024 ]; then
        human=$(awk "BEGIN {printf \"%.2f KB\", $size/1024}")
      else
        human="${size} B"
      fi
      printf "%-12s  %s\n" "$human" "$filepath"
    done

echo ""
echo "Done."
