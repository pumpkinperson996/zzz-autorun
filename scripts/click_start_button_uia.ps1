param(
    [Parameter(Mandatory = $true)]
    [long]$Hwnd,

    [switch]$LocateOnly
)

$ErrorActionPreference = 'Stop'
$targetName = -join @(
    [char]0x542F,
    [char]0x52A8,
    [char]0x4E00,
    [char]0x6761,
    [char]0x9F99
)

try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes

    $root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Hwnd)
    if ($null -eq $root) {
        Write-Output 'RETRY:UIA_NO_ROOT'
        exit 2
    }

    $idCondition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
        'start_button'
    )
    $button = $root.FindFirst(
        [System.Windows.Automation.TreeScope]::Descendants,
        $idCondition
    )

    if ($null -eq $button) {
        $nameCondition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            $targetName
        )
        $button = $root.FindFirst(
            [System.Windows.Automation.TreeScope]::Descendants,
            $nameCondition
        )
    }

    if ($null -eq $button) {
        Write-Output 'RETRY:UIA_BUTTON_NOT_FOUND'
        exit 2
    }

    if ($button.Current.Name -ne $targetName) {
        Write-Output 'RETRY:UIA_BUTTON_NOT_READY'
        exit 2
    }
    if (-not $button.Current.IsEnabled -or $button.Current.IsOffscreen) {
        Write-Output 'RETRY:UIA_BUTTON_UNAVAILABLE'
        exit 2
    }

    $rect = $button.Current.BoundingRectangle
    if ($rect.IsEmpty -or $rect.Width -le 0 -or $rect.Height -le 0) {
        Write-Output 'RETRY:UIA_EMPTY_RECT'
        exit 2
    }

    $x = [int][Math]::Round($rect.X + $rect.Width / 2)
    $y = [int][Math]::Round($rect.Y + $rect.Height / 2)
    if ($LocateOnly) {
        Write-Output "OK:UIA:x=$x,y=$y"
        exit 0
    }

    $pattern = $button.GetCurrentPattern(
        [System.Windows.Automation.InvokePattern]::Pattern
    )
    if ($null -eq $pattern) {
        Write-Output 'RETRY:UIA_INVOKE_UNAVAILABLE'
        exit 2
    }

    $pattern.Invoke()
    Write-Output "OK:UIA:x=$x,y=$y"
    exit 0
}
catch {
    $message = $_.Exception.Message -replace '[\r\n]+', ' '
    Write-Output "ERROR:UIA:$message"
    exit 3
}
