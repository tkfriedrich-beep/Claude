#!/bin/bash

SOURCE="/Volumes/Seagate Desktop Drive"
DEST="$HOME/Desktop/Photos"
MIN_SIZE_MB=1
LOGFILE="$DEST/.copied_files.log"

# Photo extensions to search for (case-insensitive)
EXTENSIONS=(
  jpg jpeg png tiff tif bmp gif webp heic heif
  arw cr2 cr3 nef nrw orf raf rw2 pef srw dng raw
  svg ico psd ai eps
)

# Directories and filenames to skip (thumbnails, system files, caches)
SKIP_DIRS=(
  ".thumbnails" "Thumbs" ".Spotlight-V100" ".fseventsd"
  ".Trashes" ".TemporaryItems" "@eaDir" "#recycle"
  "__MACOSX" ".AppleDouble"
)

SKIP_FILES=(
  "Thumbs.db" ".DS_Store" ".localized" "desktop.ini"
  ".BridgeSort" ".BridgeLabelsAndRatings"
)

# Check that the drive is mounted
if [ ! -d "$SOURCE" ]; then
  echo "ERROR: Drive not found at: $SOURCE"
  echo "Make sure the external drive is connected and mounted."
  echo ""
  echo "Available volumes:"
  ls /Volumes/
  exit 1
fi

# Create destination folder
mkdir -p "$DEST"

# Create log file if it doesn't exist
touch "$LOGFILE"

# Build the find expression for extensions
find_args=()
for i in "${!EXTENSIONS[@]}"; do
  ext="${EXTENSIONS[$i]}"
  if [ "$i" -gt 0 ]; then
    find_args+=("-o")
  fi
  find_args+=("-iname" "*.${ext}")
done

# Build the -path prune expressions for skipped directories
prune_args=()
for dir in "${SKIP_DIRS[@]}"; do
  if [ ${#prune_args[@]} -gt 0 ]; then
    prune_args+=("-o")
  fi
  prune_args+=("-iname" "$dir")
done

# Count eligible files (after all filters)
echo "Scanning drive for photos..."
echo "  Minimum file size: ${MIN_SIZE_MB} MB"
echo "  Skipping: thumbnails, system files, already-copied files"
echo ""

file_count=$(find "$SOURCE" \
  \( -type d \( "${prune_args[@]}" \) -prune \) \
  -o \( -type f -size +${MIN_SIZE_MB}M \( "${find_args[@]}" \) -print \) \
  2>/dev/null | wc -l | tr -d ' ')

echo "Found $file_count photo(s) matching filters. Processing..."
echo ""

copied=0
skipped=0
errors=0
already=0

find "$SOURCE" \
  \( -type d \( "${prune_args[@]}" \) -prune \) \
  -o \( -type f -size +${MIN_SIZE_MB}M \( "${find_args[@]}" \) -print \) \
  2>/dev/null | while IFS= read -r filepath; do

  filename=$(basename "$filepath")

  # Skip system files by name
  skip=false
  for sf in "${SKIP_FILES[@]}"; do
    if [ "$filename" = "$sf" ]; then
      skip=true
      break
    fi
  done

  # Skip macOS resource fork files (._prefix)
  if [[ "$filename" == ._* ]]; then
    skip=true
  fi

  if $skip; then
    ((skipped++))
    continue
  fi

  # Skip files already copied (check by source path in log)
  if grep -qFx "$filepath" "$LOGFILE" 2>/dev/null; then
    ((already++))
    printf "\r[Skipped already copied] %s" "$filename"
    continue
  fi

  dest_path="$DEST/$filename"

  # Handle duplicate filenames
  if [ -e "$dest_path" ]; then
    name="${filename%.*}"
    ext="${filename##*.}"
    counter=1
    while [ -e "$DEST/${name}_${counter}.${ext}" ]; do
      ((counter++))
    done
    dest_path="$DEST/${name}_${counter}.${ext}"
  fi

  if cp "$filepath" "$dest_path" 2>/dev/null; then
    ((copied++))
    echo "$filepath" >> "$LOGFILE"
    printf "\r[%d copied | %d skipped] Copied: %s" "$copied" "$already" "$filename"
  else
    ((errors++))
  fi
done

echo ""
echo ""
echo "Done!"
echo "  Copied:          $copied"
echo "  Already copied:  $already"
echo "  Skipped (junk):  $skipped"
echo "  Errors:          $errors"
echo "  Destination:     $DEST"
