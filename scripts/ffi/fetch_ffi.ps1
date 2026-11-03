param(
    # Runtime root that receives FFI headers, libraries, and license files.
    # 接收 FFI 头文件、动态库与授权文件的运行根目录。
    [string]$RuntimeRoot = "output",
    # GitHub repository that publishes LuaSkills FFI SDK assets.
    # 发布 LuaSkills FFI SDK 资产的 GitHub 仓库。
    [string]$LuaSkillsRepo = "LuaSkills/luaskills",
    # Exact GitHub Release tag of the FFI SDK asset; empty selects the newest published patch of the SDK core series.
    # FFI SDK 资产的精确 GitHub Release 标签；为空时选择 SDK 核心系列最新已发布的补丁版本。
    [string]$LuaSkillsVersion = "",
    # Directory of the SDK's embedded contract copy, which names the core series and the required contract digest.
    # SDK 嵌入式契约副本所在目录，其中给出核心系列及必需的契约摘要。
    [string]$ContractDirectory = ""
)

$ErrorActionPreference = "Stop"

# Dedicated failure type emitted only when a resolved GitHub Release lacks the requested asset.
# 仅在已解析的 GitHub Release 缺少所请求资产时发出的专用失败类型。
class ReleaseAssetNotFoundException : System.Exception {
    # Create one classified missing-asset failure with the supplied diagnostic message.
    # 使用给定诊断消息创建一个已分类的资产缺失失败。
    ReleaseAssetNotFoundException([string]$Message) : base($Message) {}
}

function Resolve-ProjectRoot {
    <#
    .SYNOPSIS
    Resolve the repository or packaged demo root from script metadata or the caller location.
    从脚本元数据或调用方位置解析仓库根目录或已发布 demo 包根目录。

    .PARAMETER ScriptDirectory
    Directory that contains the current script when PowerShell exposes it.
    PowerShell 可用时当前脚本所在的目录。

    .OUTPUTS
    Root path that contains either Cargo.toml plus scripts, or packaged scripts.
    包含 Cargo.toml 与 scripts 的仓库根路径，或包含发布脚本的包根路径。
    #>
    param([string]$ScriptDirectory)

    $Candidates = @()
    if ($ScriptDirectory) {
        $Candidates += $ScriptDirectory
    }
    $Candidates += (Get-Location).Path

    foreach ($Candidate in $Candidates) {
        $Current = $Candidate
        while ($Current) {
            $RepositoryMarkers = @("Cargo.toml", "pyproject.toml", "package.json", "go.mod")
            $IsRepositoryRoot = (Test-Path -LiteralPath (Join-Path $Current "scripts")) -and ($RepositoryMarkers | Where-Object {
                Test-Path -LiteralPath (Join-Path $Current $_)
            } | Select-Object -First 1)
            if ($IsRepositoryRoot) {
                return $Current
            }
            $PackagedFetchScript = Join-Path $Current "scripts\ffi\fetch_ffi.ps1"
            if ((Test-Path -LiteralPath $PackagedFetchScript) -and (Test-Path -LiteralPath (Join-Path $Current "runtime"))) {
                return $Current
            }
            $Parent = Split-Path -Parent $Current
            if (-not $Parent -or $Parent -eq $Current) {
                break
            }
            $Current = $Parent
        }
    }

    throw "Unable to resolve project root from script or current directory."
}

function Ensure-Dir {
    <#
    .SYNOPSIS
    Create one directory when it does not exist.
    在目录不存在时创建该目录。

    .PARAMETER Path
    Directory path to create.
    需要创建的目录路径。
    #>
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Get-PlatformKey {
    <#
    .SYNOPSIS
    Resolve the current platform key used by luaskills FFI SDK assets.
    解析当前平台对应的 luaskills FFI SDK 资产标识。

    .OUTPUTS
    Platform key such as windows-x64 or linux-arm64.
    类似 windows-x64 或 linux-arm64 的平台标识。
    #>
    $Arch = [System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLowerInvariant()
    switch ($Arch) {
        "x64" { $ArchKey = "x64" }
        "arm64" { $ArchKey = "arm64" }
        default { throw "Unsupported architecture: $Arch" }
    }

    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
        if ($ArchKey -ne "x64") {
            throw "Windows FFI SDK assets currently support x64 only."
        }
        return "windows-x64"
    }
    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::OSX)) {
        return "macos-$ArchKey"
    }
    if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Linux)) {
        return "linux-$ArchKey"
    }
    throw "Unsupported operating system."
}

function Get-ReleaseAssetInfo {
    <#
    .SYNOPSIS
    Find one exact GitHub Release asset download URL and API digest.
    查找一个精确 GitHub Release 资产下载地址与 API 摘要。

    .PARAMETER Repo
    GitHub repository in owner/name form.
    owner/name 形式的 GitHub 仓库。

    .PARAMETER Tag
    Release tag name.
    Release 标签名。

    .PARAMETER AssetName
    Exact asset file name.
    精确资产文件名。
    #>
    param(
        [string]$Repo,
        [string]$Tag,
        [string]$AssetName
    )

    $ApiUrl = "https://api.github.com/repos/$Repo/releases/tags/$Tag"
    $Release = Invoke-RestMethod -Uri $ApiUrl -UseBasicParsing
    $Asset = $Release.assets | Where-Object { $_.name -eq $AssetName } | Select-Object -First 1
    if (-not $Asset) {
        $Available = ($Release.assets | ForEach-Object { $_.name }) -join ", "
        throw [ReleaseAssetNotFoundException]::new(
            "Asset '$AssetName' not found in $Repo@$Tag. Available: $Available"
        )
    }
    return [PSCustomObject]@{
        Url = $Asset.browser_download_url
        Digest = [string]$Asset.digest
    }
}

function Convert-TagToSemVer {
    <#
    .SYNOPSIS
    Convert one Git tag such as v0.9.0 into a semantic-version object.
    将形如 v0.9.0 的 Git 标签转换为语义化版本对象。

    .PARAMETER Tag
    Git tag text to normalize and parse.
    需要规范化并解析的 Git 标签文本。
    #>
    param([string]$Tag)

    $Normalized = if ($Tag.StartsWith("v")) { $Tag.Substring(1) } else { $Tag }
    if ($Normalized -notmatch '^\d+\.\d+\.\d+$') {
        throw "Unsupported semantic version tag: $Tag"
    }
    return [System.Version]$Normalized
}

function Resolve-ReleaseTagForSeries {
    <#
    .SYNOPSIS
    Resolve the newest published GitHub release tag inside one major.minor series.
    解析一个 major.minor 系列内最新的已发布 GitHub release 标签。

    .PARAMETER Repo
    GitHub repository in owner/name form.
    owner/name 形式的 GitHub 仓库。

    .PARAMETER Series
    Major.minor series such as 0.9.
    形如 0.9 的 major.minor 系列。
    #>
    param(
        [string]$Repo,
        [string]$Series
    )

    if ($Series -notmatch '^\d+\.\d+$') {
        throw "Unsupported core series: $Series"
    }

    $ApiUrl = "https://api.github.com/repos/$Repo/releases?per_page=100"
    $Releases = Invoke-RestMethod -Uri $ApiUrl -UseBasicParsing
    # Eligible collects published final releases of the series in one array materialization.
    # Eligible 通过一次数组物化收集该系列已发布的正式 release。
    $Eligible = @(
        foreach ($Release in $Releases) {
            if ($Release.draft -or $Release.prerelease) {
                continue
            }
            $TagName = [string]$Release.tag_name
            try {
                $Version = Convert-TagToSemVer -Tag $TagName
            } catch {
                continue
            }
            if ("$($Version.Major).$($Version.Minor)" -ne $Series) {
                continue
            }
            [PSCustomObject]@{
                Tag = $TagName
                Version = $Version
            }
        }
    )

    if ($Eligible.Count -eq 0) {
        throw "No published release found for $Repo series $Series"
    }

    return ($Eligible | Sort-Object Version -Descending | Select-Object -First 1).Tag
}

function ConvertFrom-ContractDigest {
    <#
    .SYNOPSIS
    Parse one contract.sha256 file of the form "<sha256>  contract.json" into its lowercase digest.
    将 "<sha256>  contract.json" 形式的 contract.sha256 文件解析为小写摘要。

    .PARAMETER Path
    contract.sha256 file path.
    contract.sha256 文件路径。
    #>
    param([string]$Path)

    $Fields = @((Get-Content -Raw -LiteralPath $Path).Trim() -split '\s+')
    if ($Fields.Count -ne 2 -or $Fields[1] -cne "contract.json" -or $Fields[0] -notmatch '^[0-9a-fA-F]{64}$') {
        throw "Malformed contract digest file: $Path"
    }
    return $Fields[0].ToLowerInvariant()
}

function Get-SdkContractIdentity {
    <#
    .SYNOPSIS
    Read the core series and contract digest from the SDK's embedded contract copy.
    从 SDK 嵌入式契约副本读取核心系列及契约摘要。

    .PARAMETER Directory
    Directory holding contract.json and contract.sha256.
    保存 contract.json 与 contract.sha256 的目录。
    #>
    param([string]$Directory)

    $ContractPath = Join-Path $Directory "contract.json"
    $DigestPath = Join-Path $Directory "contract.sha256"
    if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf) -or -not (Test-Path -LiteralPath $DigestPath -PathType Leaf)) {
        throw "SDK embedded contract copy was not found in $Directory"
    }
    $Series = [string](Get-Content -Raw -LiteralPath $ContractPath | ConvertFrom-Json).core_series
    if ($Series -notmatch '^\d+\.\d+$') {
        throw "SDK embedded contract has no valid core_series: $Series"
    }
    $Digest = ConvertFrom-ContractDigest -Path $DigestPath
    if ($Digest -ne (Get-FileSha256Hex -Path $ContractPath)) {
        throw "SDK embedded contract copy does not match its contract.sha256 in $Directory"
    }
    return [PSCustomObject]@{
        Series = $Series
        Digest = $Digest
    }
}

function Get-FileSha256Hex {
    <#
    .SYNOPSIS
    Resolve one file SHA-256 digest with a portable fallback for older Windows PowerShell hosts.
    使用兼容旧版 Windows PowerShell 宿主的回退路径解析单个文件的 SHA-256 摘要。

    .PARAMETER Path
    File path whose SHA-256 digest should be returned as lowercase hexadecimal text.
    需要以小写十六进制文本返回 SHA-256 摘要的文件路径。
    #>
    param([string]$Path)

    $GetFileHashCommand = Get-Command -Name "Get-FileHash" -ErrorAction SilentlyContinue
    if ($GetFileHashCommand) {
        return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    }

    $Sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $Stream = [System.IO.File]::OpenRead($Path)
        try {
            $DigestBytes = $Sha256.ComputeHash($Stream)
        } finally {
            $Stream.Dispose()
        }
    } finally {
        $Sha256.Dispose()
    }

    $Builder = New-Object -TypeName System.Text.StringBuilder
    foreach ($Byte in $DigestBytes) {
        [void]$Builder.AppendFormat("{0:x2}", $Byte)
    }
    return $Builder.ToString()
}

function Save-ReleaseAssetWithDigest {
    <#
    .SYNOPSIS
    Download one GitHub Release asset and verify its GitHub API digest.
    下载单个 GitHub Release 资产并校验其 GitHub API 摘要。

    .PARAMETER Repo
    GitHub repository in owner/name form.
    owner/name 形式的 GitHub 仓库。

    .PARAMETER Tag
    Release tag name.
    Release 标签名。

    .PARAMETER AssetName
    Exact asset file name.
    精确资产文件名。

    .PARAMETER Destination
    Local destination file path.
    本地目标文件路径。
    #>
    param(
        [string]$Repo,
        [string]$Tag,
        [string]$AssetName,
        [string]$Destination
    )

    $AssetInfo = Get-ReleaseAssetInfo -Repo $Repo -Tag $Tag -AssetName $AssetName
    if ($AssetInfo.Digest -notlike "sha256:*") {
        throw "GitHub API digest for $AssetName is missing or unsupported: $($AssetInfo.Digest)"
    }
    Invoke-WebRequest -Uri $AssetInfo.Url -OutFile $Destination -UseBasicParsing
    $Expected = $AssetInfo.Digest.Substring("sha256:".Length).ToLowerInvariant()
    $Actual = Get-FileSha256Hex -Path $Destination
    if ($Expected -ne $Actual) {
        throw "SHA-256 mismatch for $AssetName. Expected $Expected, got $Actual"
    }
}

function Expand-ArchiveSmart {
    <#
    .SYNOPSIS
    Extract a .zip or .tar.gz archive.
    解压 .zip 或 .tar.gz 压缩包。

    .PARAMETER ArchivePath
    Archive path to extract.
    需要解压的压缩包路径。

    .PARAMETER Destination
    Destination directory.
    目标目录。
    #>
    param(
        [string]$ArchivePath,
        [string]$Destination
    )

    Ensure-Dir $Destination
    if ($ArchivePath.EndsWith(".zip", [System.StringComparison]::OrdinalIgnoreCase)) {
        Expand-Archive -Path $ArchivePath -DestinationPath $Destination -Force
    } else {
        tar -xzf $ArchivePath -C $Destination
    }
}

function Get-LuaSkillsLibraryCandidates {
    <#
    .SYNOPSIS
    Resolve the candidate LuaSkills dynamic library names for the current platform.
    解析当前平台对应的 LuaSkills 动态库候选名称。

    .OUTPUTS
    Ordered string array of candidate dynamic library file names.
    按顺序返回候选动态库文件名字符串数组。
    #>
    $Platform = Get-PlatformKey
    switch ($Platform) {
        "windows-x64" { return @("luaskills.dll", "libluaskills.dll") }
        "linux-x64" { return @("libluaskills.so", "luaskills.so") }
        "linux-arm64" { return @("libluaskills.so", "luaskills.so") }
        "macos-x64" { return @("libluaskills.dylib", "luaskills.dylib") }
        "macos-arm64" { return @("libluaskills.dylib", "luaskills.dylib") }
        default { throw "Unsupported LuaSkills FFI platform: $Platform" }
    }
}

function Test-ExistingLuaSkillsFfiContent {
    <#
    .SYNOPSIS
    Check whether the runtime root already contains one LuaSkills core dynamic library.
    检查运行根目录是否已经包含一个 LuaSkills core 动态库。

    .PARAMETER RuntimeRootPath
    Runtime root to inspect for installed LuaSkills libraries.
    需要检查已安装 LuaSkills 动态库的运行根目录。

    .OUTPUTS
    Boolean value that indicates whether one candidate library already exists.
    表示候选动态库是否已存在的布尔值。
    #>
    param([string]$RuntimeRootPath)

    $LibsDir = Join-Path $RuntimeRootPath "libs"
    foreach ($Candidate in Get-LuaSkillsLibraryCandidates) {
        if (Test-Path -LiteralPath (Join-Path $LibsDir $Candidate)) {
            return $true
        }
    }
    return $false
}

function Install-LuaSkillsFfi {
    <#
    .SYNOPSIS
    Download and install one luaskills FFI SDK archive into the runtime root.
    下载并安装一个 luaskills FFI SDK 归档到运行根目录。

    .PARAMETER RuntimeRootPath
    Runtime root that receives include, libs, and luaskills-ffi license material.
    接收 include、libs 与 luaskills-ffi 授权材料的运行根目录。
    #>
    param([string]$RuntimeRootPath)

    $Platform = Get-PlatformKey
    $AssetName = "luaskills-ffi-sdk-$Platform.tar.gz"
    $TempDir = Join-Path $env:TEMP "luaskills_ffi_sdk_$PID"
    $ArchivePath = Join-Path $TempDir $AssetName
    $ExtractDir = Join-Path $TempDir "extract"

    if (Test-Path -LiteralPath $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force
    }
    Ensure-Dir $TempDir

    try {
        try {
            Save-ReleaseAssetWithDigest -Repo $LuaSkillsRepo -Tag $LuaSkillsVersion -AssetName $AssetName -Destination $ArchivePath
        } catch [ReleaseAssetNotFoundException] {
            if (Test-ExistingLuaSkillsFfiContent -RuntimeRootPath $RuntimeRootPath) {
                Write-Warning "LuaSkills FFI SDK asset '$AssetName' was not found in $LuaSkillsRepo@$LuaSkillsVersion. Existing packaged LuaSkills core content will be used."
                return
            }
            throw
        }
        Expand-ArchiveSmart -ArchivePath $ArchivePath -Destination $ExtractDir

        # The archive's contract digest must equal the SDK's before any file reaches the runtime root.
        # 在任何文件进入运行根之前，归档的契约摘要必须等于 SDK 的契约摘要。
        $ArchiveDigestPath = Join-Path $ExtractDir "contracts\embedded\v1\contract.sha256"
        if (-not (Test-Path -LiteralPath $ArchiveDigestPath -PathType Leaf)) {
            throw "Downloaded $AssetName ($LuaSkillsVersion) does not contain contracts/embedded/v1/contract.sha256"
        }
        $ArchiveDigest = ConvertFrom-ContractDigest -Path $ArchiveDigestPath
        if ($ArchiveDigest -ne $ContractIdentity.Digest) {
            throw "LuaSkills core $LuaSkillsVersion embedded contract SHA-256 $ArchiveDigest does not match this SDK's contract $($ContractIdentity.Digest)"
        }

        # Exact extracted core library required before any SDK content is copied into an existing runtime root.
        # 在任何 SDK 内容复制到现有运行根之前必须存在的精确解压核心库。
        $ExtractedLibrary = Get-LuaSkillsLibraryCandidates |
            ForEach-Object { Join-Path (Join-Path $ExtractDir "lib") $_ } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if (-not $ExtractedLibrary) {
            throw "LuaSkills dynamic library was not found in downloaded $AssetName"
        }

        $IncludeSource = Join-Path $ExtractDir "include"
        if (Test-Path -LiteralPath $IncludeSource) {
            $IncludeDest = Join-Path $RuntimeRootPath "include"
            Ensure-Dir $IncludeDest
            Copy-Item -Recurse -Force -Path (Join-Path $IncludeSource "*") -Destination $IncludeDest -ErrorAction Stop
        }

        $LibrarySource = Join-Path $ExtractDir "lib"
        if (Test-Path -LiteralPath $LibrarySource) {
            $LibraryDest = Join-Path $RuntimeRootPath "libs"
            Ensure-Dir $LibraryDest
            Copy-Item -Recurse -Force -Path (Join-Path $LibrarySource "*") -Destination $LibraryDest -ErrorAction Stop
        }

        $LicenseSource = Join-Path $ExtractDir "licenses"
        if (Test-Path -LiteralPath $LicenseSource) {
            $LicenseDest = Join-Path $RuntimeRootPath "licenses\luaskills-ffi"
            Ensure-Dir $LicenseDest
            Copy-Item -Recurse -Force -Path (Join-Path $LicenseSource "*") -Destination $LicenseDest -ErrorAction Stop
        }

    } finally {
        Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } elseif ($PSCommandPath) { Split-Path -Parent $PSCommandPath } elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path } else { "" }
$ProjectRoot = Resolve-ProjectRoot -ScriptDirectory $ScriptDir
Set-Location $ProjectRoot
if ([string]::IsNullOrWhiteSpace($ContractDirectory)) {
    $ContractDirectory = Join-Path $ProjectRoot "src\luaskills\contracts\embedded\v1"
}
# ContractIdentity is the SDK's core series and contract digest; the downloaded core must match both.
# ContractIdentity 是 SDK 的核心系列及契约摘要；下载的核心必须同时匹配二者。
$ContractIdentity = Get-SdkContractIdentity -Directory $ContractDirectory
if ([string]::IsNullOrWhiteSpace($LuaSkillsVersion)) {
    $LuaSkillsVersion = Resolve-ReleaseTagForSeries -Repo $LuaSkillsRepo -Series $ContractIdentity.Series
} elseif (-not ($LuaSkillsVersion -cmatch '^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') -or "$($Matches[1]).$($Matches[2])" -ne $ContractIdentity.Series) {
    throw "LuaSkills core tag $LuaSkillsVersion is outside the SDK core series $($ContractIdentity.Series); expected v$($ContractIdentity.Series).<patch>"
}
Ensure-Dir $RuntimeRoot
Install-LuaSkillsFfi -RuntimeRootPath $RuntimeRoot
Write-Host "LuaSkills FFI SDK installed into $RuntimeRoot"
