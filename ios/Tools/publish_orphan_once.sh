#!/usr/bin/env bash
# Must be used ONLY in an authorized GitHub environment with git push access.
# Exactly one empty-history root commit, exactly one push. DO NOT run here.
set -euo pipefail
SOURCE=${1:?Use: publish_orphan_once.sh /path/to/PoPTST-integrated}
REPO=${2:-https://github.com/joao9vegeto-stack/KintTany.git}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
git clone --filter=blob:none "$REPO" "$WORK/repo"
cd "$WORK/repo"
if git ls-remote --exit-code --heads origin PoPTST; then
    echo 'REFUSE: PoPTST already exists; no additional commit/workflow' >&2; exit 1
fi
git switch --orphan PoPTST
# Wipe index and working tree from prior branch; preserve .git.
git rm -rf --cached . >/dev/null 2>&1 || true
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf -- {} +
cp -R "$SOURCE"/. .
find . -name '__pycache__' -type d -prune -exec rm -rf {} +
find . -name '*.pyc' -delete
git add -A
test "$(git rev-list --count HEAD 2>/dev/null || echo 0)" != 1 || true
git -c user.name='PoPTST Build' -c user.email='actions@users.noreply.github.com' commit -m 'PoPTST: Xbox retail native iOS Vulkan-KosmicKrisp static recomp integration'
test "$(git rev-list --parents -n 1 HEAD | wc -w | tr -d ' ')" = 1
# Only one remote mutation; this starts exactly one workflow.
git push --porcelain origin HEAD:refs/heads/PoPTST
