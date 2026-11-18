#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: publish-image-release.sh TAG RELEASE_DIR' >&2; exit 2; }
tag=$1
release_dir=$2
repo=${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY}
commit=$(git rev-parse HEAD)
version=$(cat IMAGE_VERSION)
[[ $tag == "image-v$version" ]] || { echo 'Tag does not match IMAGE_VERSION.' >&2; exit 1; }

check_current_version() {
    local current_version
    current_version=$(gh api -H 'Accept: application/vnd.github.raw+json' \
        "repos/$repo/contents/IMAGE_VERSION?ref=main") || exit 1
    if [[ $current_version != "$version" ]]; then
        echo "Image $version was superseded by $current_version. Skipping publication."
        exit 0
    fi
}

check_current_version
assets=(boot.img vendor_boot.img recovery.img vbmeta.img sparse_root.img.zst build-result.json SHA256SUMS)
(cd "$release_dir" && sha256sum -c SHA256SUMS)
for index in "${!assets[@]}"; do
    assets[$index]="$release_dir/${assets[$index]}"
done

# A failed or cancelled upload can leave a draft. Resume only the same commit.
draft=$(gh release list --repo "$repo" --limit 100 --json tagName,isDraft \
    --jq ".[] | select(.tagName == \"$tag\") | .isDraft")
if [[ $draft == false ]]; then
    echo "Release $tag is already published."
    exit 0
fi
if tag_commit=$(git rev-parse --verify --quiet "refs/tags/$tag^{commit}") && [[ $tag_commit != "$commit" ]]; then
    echo "Tag $tag already points to a different commit." >&2
    exit 1
fi

range=$commit
if previous=$(git describe --tags --abbrev=0 --match 'image-v*' --exclude "$tag" "$commit"); then
    range="$previous..$commit"
fi
notes=$(mktemp)
trap 'rm -f -- "$notes"' EXIT
{
    printf '镜像版本 `%s`，源码提交 [`%s`](%s/%s/commit/%s)。\n\n' "$version" "${commit:0:12}" "${GITHUB_SERVER_URL:-https://github.com}" "$repo" "$commit"
    printf '下载本页的刷机镜像后，先运行 `sha256sum -c SHA256SUMS`，再用 `zstd -d sparse_root.img.zst` 解压。\n\n'
    printf '构建已通过自动镜像校验，实机启动未测。[刷机说明](%s/%s/blob/%s/docs/flashing.md)。\n\n' "${GITHUB_SERVER_URL:-https://github.com}" "$repo" "$commit"
    printf '## 提交记录\n\n'
    git log --format='### %s (`%h`)%n%n%b' "$range"
} > "$notes"

if [[ $draft == true ]]; then
    target=$(gh release view "$tag" --repo "$repo" --json targetCommitish --jq .targetCommitish)
    [[ $target == "$commit" ]] || { echo "Draft $tag targets a different commit." >&2; exit 1; }
    gh release upload "$tag" "${assets[@]}" --clobber --repo "$repo"
else
    gh release create "$tag" "${assets[@]}" --draft --repo "$repo" \
        --target "$commit" --title "Negroni Arch Linux $version" --notes-file "$notes"
fi
check_current_version
gh release edit "$tag" --draft=false --notes-file "$notes" --repo "$repo"
