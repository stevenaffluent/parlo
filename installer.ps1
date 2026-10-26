# Parlo installer: a graphical setup window (WPF, built into Windows) that installs a private
# Python 3.11, the libraries and the models into this folder, then adds shortcuts.
#   installer.ps1              normal install
#   installer.ps1 -Preview     walk through the screens with simulated steps (installs nothing)
#   installer.ps1 -Preview -Snapshot <folder>   also save PNGs of each screen, then close
# setup.ps1 is the plain console version of the same steps.
param([switch]$Preview, [string]$Snapshot = "")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

# ---------------------------------------------------------------- steps -----
$Steps = @(
    @{ id = "python";  name = "Python 3.11";                  weight = 8  },
    @{ id = "venv";    name = "Private Python environment";   weight = 4  },
    @{ id = "torch";   name = "PyTorch (speech engine)";      weight = 28 },
    @{ id = "libs";    name = "Speech and AI libraries";      weight = 22 },
    @{ id = "speech";  name = "Bark 3.0 speech model";        weight = 10 },
    @{ id = "unpack";  name = "Preparing the speech model";   weight = 14 },
    @{ id = "llm";     name = "AI writing model (Qwen2.5)";   weight = 12 },
    @{ id = "links";   name = "Shortcuts";                    weight = 2  }
)
$sync = [hashtable]::Synchronized(@{
    state = @("pending") * $Steps.Count; detail = @("") * $Steps.Count; frac = 0.0; current = -1
    status = ""; phase = "welcome"; error = ""; cancel = $false; proc = $null
    log = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
})

# The install work runs in a background runspace and only writes plain data into $sync;
# a timer on the window thread reads it and updates the screen.
$Worker = {
    param($sync, $Steps, $Root, $Preview, $Desktop, $StartMenu, $From)
    $logFile = Join-Path $Root "data\setup-log.txt"
    New-Item -ItemType Directory -Force (Join-Path $Root "data") | Out-Null
    function Log($line) { [void]$sync.log.Add($line); Add-Content -Path $logFile -Value $line -Encoding UTF8 }
    function Status($text) { $sync.status = $text }

    # Run a program, stream its output into the log, and turn progress lines into numbers.
    function Run($exe, $arguments, $expectFiles = 0) {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "cmd.exe"
        $psi.Arguments = "/c `"`"$exe`" $arguments 2>&1`""
        $psi.RedirectStandardOutput = $true; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
        $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
        $psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1"; $psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
        $p = [Diagnostics.Process]::Start($psi); $sync.proc = $p
        $files = 0
        while ($null -ne ($line = $p.StandardOutput.ReadLine())) {
            if ($line -match '^@progress ([\d.]+)') { $sync.frac = [double]$Matches[1]; continue }
            if ($line -match '^@status (.+)') { Status $Matches[1]; Log $Matches[1]; continue }
            if ($line -match '^Progress (\d+) of (\d+)') {
                $part = [double]$Matches[1] / [math]::Max(1, [double]$Matches[2])
                $sync.frac = if ($expectFiles) { [math]::Min(0.97, ($files - 1 + $part) / $expectFiles) } else { [math]::Min(0.97, $part) }
                continue
            }
            Log $line
            if ($line -match '^\s*Downloading (\S+?)(-\d[^\s]*)?(\.whl|\.tar\.gz)? \(([^)]+)\)') {
                $files++; Status "Downloading $($Matches[1]) ($($Matches[4]))"
                if ($expectFiles) { $sync.frac = [math]::Min(0.97, $files / $expectFiles) }
            } elseif ($line -match '^Installing collected packages') { Status "Installing packages..."; $sync.frac = [math]::Max($sync.frac, 0.97) }
            elseif ($line -match '^(Collecting|Requirement already satisfied): ?(\S+)') { Status "Checking $($Matches[2])" }
            if ($sync.cancel) { try { $p.Kill() } catch {} }
        }
        $p.WaitForExit(); $sync.proc = $null
        return $p.ExitCode
    }
    function HasPy311 {
        try { $c = Start-Process -FilePath "py" -ArgumentList "-3.11 -c pass" -WindowStyle Hidden -Wait -PassThru -ErrorAction Stop; return ($c.ExitCode -eq 0) }
        catch { return $false }  # no py launcher at all yet
    }

    $py = Join-Path $Root ".venv\Scripts\python.exe"
    for ($i = $From; $i -lt $Steps.Count; $i++) {
        if ($sync.cancel) { return }
        $id = $Steps[$i].id
        $sync.current = $i; $sync.state[$i] = "active"; $sync.frac = 0; $sync.detail[$i] = ""
        Log "==> $($Steps[$i].name)"
        try {
            if ($Preview) {  # simulated step for previews and screenshots
                Status "Preview: $($Steps[$i].name)..."
                for ($k = 1; $k -le 10; $k++) { Start-Sleep -Milliseconds 180; $sync.frac = $k / 10; Log "  preview step $id $($k*10)%" }
            } else {
                switch ($id) {
                    "python" {
                        Status "Looking for Python 3.11"
                        if (-not (HasPy311)) {
                            if (Get-Command py -ErrorAction SilentlyContinue) { Status "Installing Python 3.11 (python.org install manager)"; [void](Run "py" "install 3.11") }
                            if (-not (HasPy311) -and (Get-Command winget -ErrorAction SilentlyContinue)) {
                                Status "Installing Python 3.11 with winget"
                                [void](Run "winget" "install -e --id Python.Python.3.11 --scope user --accept-source-agreements --accept-package-agreements")
                            }
                            if (-not (HasPy311)) { throw "Python 3.11 could not be installed automatically. Install it from python.org (tick 'py launcher'), then run Setup again." }
                        }
                        $sync.detail[$i] = "found"
                    }
                    "venv" {
                        if (-not (Test-Path $py)) { Status "Creating the environment"; if ((Run "py" "-3.11 -m venv `"$Root\.venv`"") -ne 0) { throw "Could not create the Python environment." } }
                        Status "Updating pip"; [void](Run $py "-m pip install --upgrade pip --quiet")
                    }
                    "torch" {
                        $cuda = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
                        $index = if ($cuda) { "https://download.pytorch.org/whl/cu128" } else { "https://download.pytorch.org/whl/cpu" }
                        $sync.detail[$i] = if ($cuda) { "NVIDIA GPU build" } else { "CPU build" }
                        if ((Run $py "-m pip install torch==2.8.0 --index-url $index --progress-bar raw") -ne 0) { throw "PyTorch could not be installed. Check your internet connection." }
                    }
                    "libs" { if ((Run $py "-m pip install -r `"$Root\requirements.txt`" --progress-bar raw" 60) -ne 0) { throw "Some libraries could not be installed. Check your internet connection." } }
                    "speech" { if ((Run $py "`"$Root\app\prefetch.py`" speech") -ne 0) { throw "The speech model could not be downloaded." } }
                    "unpack" { if ((Run $py "`"$Root\app\prefetch.py`" unpack") -ne 0) { throw "The speech model could not be prepared. See the details." } }
                    "llm" { [void](Run $py "`"$Root\app\prefetch.py`" llm") }
                    "links" {
                        $ws = New-Object -ComObject WScript.Shell
                        $dirs = @(); if ($Desktop) { $dirs += [Environment]::GetFolderPath("Desktop") }
                        if ($StartMenu) { $dirs += "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" }
                        foreach ($dir in $dirs) {
                            Remove-Item "$dir\Bark Dictate.lnk" -ErrorAction SilentlyContinue  # the app's earlier name
                            $lnk = $ws.CreateShortcut("$dir\Parlo.lnk")
                            $lnk.TargetPath = Join-Path $Root ".venv\Scripts\pythonw.exe"
                            $lnk.Arguments = "`"$Root\app\main.py`""
                            $lnk.WorkingDirectory = $Root
                            $lnk.IconLocation = Join-Path $Root "data\icon.ico"
                            $lnk.Save(); Log "Shortcut: $dir\Parlo.lnk"
                        }
                        $sync.detail[$i] = if ($dirs.Count) { "added" } else { "skipped" }
                    }
                }
            }
            if ($sync.cancel) { return }
            $sync.state[$i] = "done"; $sync.frac = 1
            if (-not $sync.detail[$i]) { $sync.detail[$i] = "done" }
        } catch {
            $sync.state[$i] = "failed"; $sync.error = $_.Exception.Message; Log "ERROR: $($_.Exception.Message)"
            $sync.phase = "failed"; return
        }
    }
    $sync.current = $Steps.Count; $sync.phase = "done"
}

# ---------------------------------------------------------------- window ----
[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Install Parlo" Width="880" Height="580" WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ResizeMode="NoResize" WindowStartupLocation="CenterScreen" FontFamily="Segoe UI" UseLayoutRounding="True">
  <Window.Resources>
    <SolidColorBrush x:Key="Accent" Color="#C2410C"/>
    <SolidColorBrush x:Key="Text" Color="#ECECF1"/>
    <SolidColorBrush x:Key="Muted" Color="#9A9AA6"/>
    <Style x:Key="Btn" TargetType="Button">
      <Setter Property="Foreground" Value="#ECECF1"/><Setter Property="Background" Value="#1E1E24"/>
      <Setter Property="BorderBrush" Value="#3A3A44"/><Setter Property="FontSize" Value="14"/><Setter Property="FontWeight" Value="SemiBold"/>
      <Setter Property="Padding" Value="22,10"/><Setter Property="Cursor" Value="Hand"/>
      <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button">
        <Border x:Name="b" Background="{TemplateBinding Background}" BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="1" CornerRadius="11" Padding="{TemplateBinding Padding}">
          <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/></Border>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True"><Setter TargetName="b" Property="Opacity" Value="0.88"/></Trigger>
          <Trigger Property="IsPressed" Value="True"><Setter TargetName="b" Property="Opacity" Value="0.75"/></Trigger>
        </ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter>
    </Style>
    <Style x:Key="Primary" TargetType="Button" BasedOn="{StaticResource Btn}">
      <Setter Property="Background" Value="#C2410C"/><Setter Property="BorderBrush" Value="#C2410C"/><Setter Property="Foreground" Value="White"/>
    </Style>
    <Style x:Key="Check" TargetType="CheckBox">
      <Setter Property="Foreground" Value="#ECECF1"/><Setter Property="FontSize" Value="13.5"/><Setter Property="Cursor" Value="Hand"/><Setter Property="Margin" Value="0,0,22,0"/>
      <Setter Property="Template"><Setter.Value><ControlTemplate TargetType="CheckBox">
        <StackPanel Orientation="Horizontal" Background="Transparent">
          <Border x:Name="box" Width="20" Height="20" CornerRadius="6" BorderThickness="1.5" BorderBrush="#6B6B78" Background="#1E1E24">
            <TextBlock x:Name="tick" Text="&#xE73E;" FontFamily="Segoe MDL2 Assets" FontSize="11" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center" Visibility="Collapsed"/></Border>
          <ContentPresenter Margin="9,0,0,0" VerticalAlignment="Center"/></StackPanel>
        <ControlTemplate.Triggers><Trigger Property="IsChecked" Value="True">
          <Setter TargetName="box" Property="Background" Value="#C2410C"/><Setter TargetName="box" Property="BorderBrush" Value="#C2410C"/>
          <Setter TargetName="tick" Property="Visibility" Value="Visible"/></Trigger></ControlTemplate.Triggers>
      </ControlTemplate></Setter.Value></Setter>
    </Style>
  </Window.Resources>
  <Border Margin="16" CornerRadius="20" Background="#0E0E11" BorderBrush="#2A2A32" BorderThickness="1">
    <Border.Effect><DropShadowEffect BlurRadius="28" ShadowDepth="0" Opacity="0.55" Color="Black"/></Border.Effect>
    <Grid>
      <Grid.ColumnDefinitions><ColumnDefinition Width="310"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
      <!-- brand panel -->
      <Border x:Name="BrandPanel" CornerRadius="20,0,0,20">
        <Border.Background><RadialGradientBrush Center="0.5,0.38" GradientOrigin="0.5,0.38" RadiusX="0.95" RadiusY="0.75">
          <GradientStop Color="#3A1A0C" Offset="0"/><GradientStop Color="#16120F" Offset="0.55"/><GradientStop Color="#121216" Offset="1"/></RadialGradientBrush></Border.Background>
        <Grid>
          <StackPanel VerticalAlignment="Center" HorizontalAlignment="Center">
            <Viewbox Width="132" Height="132" HorizontalAlignment="Center">
              <Canvas Width="256" Height="256">
                <Canvas.Effect><DropShadowEffect x:Name="Glow" BlurRadius="34" ShadowDepth="0" Opacity="0.75" Color="#EF7B45"/></Canvas.Effect>
                <Rectangle Width="256" Height="256" RadiusX="60" RadiusY="60" Fill="#C2410C"/>
                <Rectangle Canvas.Left="57"  Canvas.Top="52"   Width="18" Height="156"   RadiusX="9" RadiusY="9" Fill="White" RenderTransformOrigin="0.5,0.5"><Rectangle.RenderTransform><ScaleTransform x:Name="b0"/></Rectangle.RenderTransform></Rectangle>
                <Rectangle Canvas.Left="83"  Canvas.Top="64.6" Width="18" Height="94.7"  RadiusX="9" RadiusY="9" Fill="White" RenderTransformOrigin="0.5,0.5"><Rectangle.RenderTransform><ScaleTransform x:Name="b1"/></Rectangle.RenderTransform></Rectangle>
                <Rectangle Canvas.Left="107" Canvas.Top="52.1" Width="18" Height="119.8" RadiusX="9" RadiusY="9" Fill="White" RenderTransformOrigin="0.5,0.5"><Rectangle.RenderTransform><ScaleTransform x:Name="b2"/></Rectangle.RenderTransform></Rectangle>
                <Rectangle Canvas.Left="131" Canvas.Top="50.5" Width="18" Height="123"   RadiusX="9" RadiusY="9" Fill="White" RenderTransformOrigin="0.5,0.5"><Rectangle.RenderTransform><ScaleTransform x:Name="b3"/></Rectangle.RenderTransform></Rectangle>
                <Rectangle Canvas.Left="155" Canvas.Top="58.9" Width="18" Height="106.2" RadiusX="9" RadiusY="9" Fill="White" RenderTransformOrigin="0.5,0.5"><Rectangle.RenderTransform><ScaleTransform x:Name="b4"/></Rectangle.RenderTransform></Rectangle>
                <Rectangle Canvas.Left="179" Canvas.Top="85.4" Width="18" Height="53.2"  RadiusX="9" RadiusY="9" Fill="White" RenderTransformOrigin="0.5,0.5"><Rectangle.RenderTransform><ScaleTransform x:Name="b5"/></Rectangle.RenderTransform></Rectangle>
              </Canvas>
            </Viewbox>
            <TextBlock Text="Parlo" FontSize="36" FontWeight="SemiBold" Foreground="White" HorizontalAlignment="Center" Margin="0,22,0,0"/>
            <TextBlock Text="Private dictation for Windows" FontSize="14" Foreground="{StaticResource Muted}" HorizontalAlignment="Center" Margin="0,4,0,0"/>
          </StackPanel>
          <TextBlock x:Name="BrandFoot" Text="Speech and AI run on your PC. Free, offline, no account." FontSize="12" Foreground="#8D8D9A"
                     TextWrapping="Wrap" TextAlignment="Center" VerticalAlignment="Bottom" Margin="30,0,30,26"/>
        </Grid>
      </Border>
      <!-- close button -->
      <Button x:Name="CloseX" Grid.Column="1" HorizontalAlignment="Right" VerticalAlignment="Top" Margin="0,12,12,0" Width="34" Height="34"
              Background="Transparent" BorderBrush="Transparent" Foreground="#9A9AA6" Cursor="Hand" ToolTip="Close">
        <Button.Template><ControlTemplate TargetType="Button"><Border x:Name="c" Background="Transparent" CornerRadius="8">
          <TextBlock Text="&#xE8BB;" FontFamily="Segoe MDL2 Assets" FontSize="11" Foreground="#9A9AA6" HorizontalAlignment="Center" VerticalAlignment="Center"/></Border>
          <ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="c" Property="Background" Value="#24242B"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Button.Template>
      </Button>

      <!-- page 1: welcome -->
      <Grid x:Name="Welcome" Grid.Column="1" Margin="44,46,44,34">
        <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
        <TextBlock Text="Install Parlo" FontSize="30" FontWeight="SemiBold" Foreground="White"/>
        <TextBlock Grid.Row="1" TextWrapping="Wrap" FontSize="14" Foreground="{StaticResource Muted}" Margin="0,8,0,0" LineHeight="21"
                   Text="Talk, and your words appear in any app. Everything installs into this folder and runs on your own PC."/>
        <Border Grid.Row="2" Margin="0,22,0,0" CornerRadius="14" Background="#17171C" BorderBrush="#2A2A32" BorderThickness="1" Padding="18,12" VerticalAlignment="Top">
          <StackPanel x:Name="WhatList"/>
        </Border>
        <StackPanel Grid.Row="3" Orientation="Horizontal" Margin="0,20,0,0">
          <CheckBox x:Name="OptDesktop" Content="Desktop shortcut" IsChecked="True" Style="{StaticResource Check}"/>
          <CheckBox x:Name="OptStart" Content="Start Menu shortcut" IsChecked="True" Style="{StaticResource Check}"/>
        </StackPanel>
        <Grid Grid.Row="4" Margin="0,22,0,0">
          <TextBlock x:Name="Folder" VerticalAlignment="Center" FontSize="12" Foreground="#8D8D9A" TextTrimming="CharacterEllipsis" Margin="0,0,250,0"/>
          <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
            <Button x:Name="BtnCancel" Content="Cancel" Style="{StaticResource Btn}" Margin="0,0,10,0"/>
            <Button x:Name="BtnInstall" Content="Install" Style="{StaticResource Primary}" Padding="30,10"/>
          </StackPanel>
        </Grid>
      </Grid>

      <!-- page 2: installing -->
      <Grid x:Name="Progress" Grid.Column="1" Margin="44,46,44,30" Visibility="Collapsed">
        <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="*"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
        <TextBlock x:Name="ProgTitle" Text="Installing Parlo" FontSize="30" FontWeight="SemiBold" Foreground="White"/>
        <TextBlock x:Name="ProgSub" Grid.Row="1" FontSize="14" Foreground="{StaticResource Muted}" Margin="0,8,0,0" TextWrapping="Wrap"
                   Text="This takes about 15 to 30 minutes, mostly downloading. You can keep using your PC."/>
        <Grid Grid.Row="2" Margin="0,18,0,0">
          <StackPanel x:Name="StepList"/>
          <TextBox x:Name="LogBox" Visibility="Collapsed" Background="#121216" Foreground="#B8B8C4" BorderBrush="#2A2A32" FontFamily="Cascadia Mono, Consolas"
                   FontSize="11.5" IsReadOnly="True" TextWrapping="NoWrap" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Auto" Padding="10"/>
        </Grid>
        <StackPanel Grid.Row="3" Margin="0,16,0,0">
          <Grid>
            <TextBlock x:Name="Status" Foreground="#C9C9D3" FontSize="12.5" TextTrimming="CharacterEllipsis" Margin="0,0,60,0"/>
            <TextBlock x:Name="Pct" Foreground="White" FontSize="13" FontWeight="SemiBold" HorizontalAlignment="Right"/>
          </Grid>
          <Border x:Name="Track" Height="10" CornerRadius="5" Background="#24242B" Margin="0,8,0,0">
            <Border x:Name="Fill" HorizontalAlignment="Left" Width="0" CornerRadius="5">
              <Border.Background><LinearGradientBrush StartPoint="0,0" EndPoint="1,0"><GradientStop Color="#E96B32" Offset="0"/><GradientStop Color="#C2410C" Offset="1"/></LinearGradientBrush></Border.Background>
            </Border>
          </Border>
        </StackPanel>
        <Grid Grid.Row="4" Margin="0,18,0,0">
          <Button x:Name="BtnDetails" Content="Show details" Style="{StaticResource Btn}" HorizontalAlignment="Left" Padding="16,8" FontSize="13"/>
          <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
            <Button x:Name="BtnClose2" Content="Close" Style="{StaticResource Btn}" Margin="0,0,10,0" Visibility="Collapsed"/>
            <Button x:Name="BtnStop" Content="Cancel" Style="{StaticResource Btn}"/>
            <Button x:Name="BtnRetry" Content="Try again" Style="{StaticResource Primary}" Visibility="Collapsed"/>
          </StackPanel>
        </Grid>
      </Grid>

      <!-- page 3: done -->
      <Grid x:Name="Done" Grid.Column="1" Margin="44,0,44,34" Visibility="Collapsed">
        <StackPanel VerticalAlignment="Center">
          <Border x:Name="DoneBadge" Width="76" Height="76" CornerRadius="38" Background="#14382A" HorizontalAlignment="Left" RenderTransformOrigin="0.5,0.5">
            <Border.RenderTransform><ScaleTransform x:Name="BadgeScale" ScaleX="1" ScaleY="1"/></Border.RenderTransform>
            <TextBlock Text="&#xE73E;" FontFamily="Segoe MDL2 Assets" FontSize="34" Foreground="#3ECF8E" HorizontalAlignment="Center" VerticalAlignment="Center"/>
          </Border>
          <TextBlock Text="Parlo is ready" FontSize="32" FontWeight="SemiBold" Foreground="White" Margin="0,22,0,0"/>
          <StackPanel Orientation="Horizontal" Margin="0,12,0,0">
            <TextBlock Text="Press" FontSize="15" Foreground="#C9C9D3" VerticalAlignment="Center"/>
            <Border CornerRadius="7" Background="#1E1E24" BorderBrush="#3A3A44" BorderThickness="1,1,1,2.5" Padding="9,3" Margin="8,0,5,0"><TextBlock Text="Ctrl" FontSize="13" FontWeight="SemiBold" Foreground="White"/></Border>
            <Border CornerRadius="7" Background="#1E1E24" BorderBrush="#3A3A44" BorderThickness="1,1,1,2.5" Padding="9,3" Margin="0,0,8,0"><TextBlock Text="&#x229E; Win" FontSize="13" FontWeight="SemiBold" Foreground="White"/></Border>
            <TextBlock Text="in any app and start talking." FontSize="15" Foreground="#C9C9D3" VerticalAlignment="Center"/>
          </StackPanel>
          <TextBlock FontSize="13" Foreground="{StaticResource Muted}" Margin="0,10,0,0" TextWrapping="Wrap"
                     Text="Parlo lives in the system tray. It loads its speech model in about 20 seconds after starting."/>
          <StackPanel Orientation="Horizontal" Margin="0,30,0,0">
            <Button x:Name="BtnLaunch" Content="Launch Parlo" Style="{StaticResource Primary}" Padding="28,11" Margin="0,0,10,0"/>
            <Button x:Name="BtnClose3" Content="Close" Style="{StaticResource Btn}"/>
          </StackPanel>
        </StackPanel>
      </Grid>
    </Grid>
  </Border>
</Window>
'@
$win = [Windows.Markup.XamlReader]::Load((New-Object System.Xml.XmlNodeReader $xaml))
$ui = @{}
foreach ($n in "Welcome","Progress","Done","WhatList","OptDesktop","OptStart","Folder","BtnCancel","BtnInstall","CloseX","StepList","LogBox",
               "Status","Pct","Track","Fill","BtnDetails","BtnClose2","BtnStop","BtnRetry","ProgTitle","ProgSub","BtnLaunch","BtnClose3",
               "Glow","BadgeScale","b0","b1","b2","b3","b4","b5") { $ui[$n] = $win.FindName($n) }
$win.Add_MouseLeftButtonDown({ try { $win.DragMove() } catch {} })

function Brush($hex) { New-Object Windows.Media.SolidColorBrush ([Windows.Media.ColorConverter]::ConvertFromString($hex)) }
function Anim($from, $to, $secs, $repeat = $true, $begin = 0) {
    $a = New-Object Windows.Media.Animation.DoubleAnimation
    $a.From = $from; $a.To = $to; $a.Duration = New-Object Windows.Duration([TimeSpan]::FromSeconds($secs))
    $a.AutoReverse = $repeat
    if ($repeat) { $a.RepeatBehavior = [Windows.Media.Animation.RepeatBehavior]::Forever }
    $a.BeginTime = [TimeSpan]::FromSeconds($begin)
    $ease = New-Object Windows.Media.Animation.SineEase; $ease.EasingMode = "EaseInOut"; $a.EasingFunction = $ease
    return $a
}
# Logo: a slow glow on the welcome screen; the bars move like a live voice while installing.
$ui.Glow.BeginAnimation([Windows.Media.Effects.DropShadowEffect]::BlurRadiusProperty, (Anim 22 46 1.8))
function Start-Waveform {
    $lows = @(0.55, 0.35, 0.6, 0.4, 0.5, 0.3); $durs = @(0.62, 0.48, 0.71, 0.53, 0.66, 0.44)
    for ($i = 0; $i -lt 6; $i++) { $ui["b$i"].BeginAnimation([Windows.Media.ScaleTransform]::ScaleYProperty, (Anim 1 $lows[$i] $durs[$i] $true ($i * 0.07))) }
}
function Stop-Waveform { for ($i = 0; $i -lt 6; $i++) { $ui["b$i"].BeginAnimation([Windows.Media.ScaleTransform]::ScaleYProperty, $null) } }

# Welcome: what gets installed
$what = @(@("Python 3.11 runtime", "30 MB"), @("Speech and AI libraries", "1.1 GB"), @("Bark 3.0 speech model", "156 MB"), @("Qwen2.5 AI writing model", "1.0 GB"))
foreach ($w in $what) {
    $g = New-Object Windows.Controls.Grid; $g.Margin = "0,7,0,7"
    $dot = New-Object Windows.Controls.TextBlock; $dot.Text = [char]0xE73E; $dot.FontFamily = "Segoe MDL2 Assets"; $dot.FontSize = 12; $dot.Foreground = Brush "#EF7B45"; $dot.VerticalAlignment = "Center"
    $t = New-Object Windows.Controls.TextBlock; $t.Text = $w[0]; $t.Foreground = Brush "#ECECF1"; $t.FontSize = 14; $t.Margin = "26,0,0,0"
    $s = New-Object Windows.Controls.TextBlock; $s.Text = $w[1]; $s.Foreground = Brush "#9A9AA6"; $s.FontSize = 13; $s.HorizontalAlignment = "Right"
    [void]$g.Children.Add($dot); [void]$g.Children.Add($t); [void]$g.Children.Add($s); [void]$ui.WhatList.Children.Add($g)
}
$sum = New-Object Windows.Controls.TextBlock; $sum.Text = "About 2.3 GB to download and 5 GB of disk space. Nothing to configure."
$sum.Foreground = Brush "#9A9AA6"; $sum.FontSize = 12.5; $sum.Margin = "0,8,0,2"; [void]$ui.WhatList.Children.Add($sum)
$ui.Folder.Text = "Installs into  $Root"; $ui.Folder.ToolTip = $Root

# Progress: one row per step
$rows = @()
foreach ($st in $Steps) {
    $g = New-Object Windows.Controls.Grid; $g.Height = 33
    $circle = New-Object Windows.Controls.Border; $circle.Width = 20; $circle.Height = 20; $circle.CornerRadius = 10; $circle.BorderThickness = 1.5
    $circle.BorderBrush = Brush "#4A4A55"; $circle.HorizontalAlignment = "Left"; $circle.VerticalAlignment = "Center"
    $glyph = New-Object Windows.Controls.TextBlock; $glyph.FontFamily = "Segoe MDL2 Assets"; $glyph.FontSize = 10; $glyph.Foreground = Brush "White"
    $glyph.HorizontalAlignment = "Center"; $glyph.VerticalAlignment = "Center"; $circle.Child = $glyph
    $name = New-Object Windows.Controls.TextBlock; $name.Text = $st.name; $name.FontSize = 14; $name.Foreground = Brush "#8D8D9A"; $name.Margin = "34,0,0,0"; $name.VerticalAlignment = "Center"
    $det = New-Object Windows.Controls.TextBlock; $det.FontSize = 12.5; $det.Foreground = Brush "#9A9AA6"; $det.HorizontalAlignment = "Right"; $det.VerticalAlignment = "Center"
    [void]$g.Children.Add($circle); [void]$g.Children.Add($name); [void]$g.Children.Add($det); [void]$ui.StepList.Children.Add($g)
    $rows += @{ circle = $circle; glyph = $glyph; name = $name; det = $det; shown = "" }
}

function Set-Row($i, $state) {
    $r = $rows[$i]; if ($r.shown -eq $state) { return }; $r.shown = $state
    $r.circle.BeginAnimation([Windows.UIElement]::OpacityProperty, $null); $r.circle.Opacity = 1
    switch ($state) {
        "pending" { $r.circle.Background = $null; $r.circle.BorderBrush = Brush "#4A4A55"; $r.glyph.Text = ""; $r.name.Foreground = Brush "#8D8D9A"; $r.name.FontWeight = "Normal" }
        "active"  { $r.circle.Background = Brush "#C2410C"; $r.circle.BorderBrush = Brush "#C2410C"; $r.glyph.Text = ""; $r.name.Foreground = Brush "White"; $r.name.FontWeight = "SemiBold"
                    $r.circle.BeginAnimation([Windows.UIElement]::OpacityProperty, (Anim 1 0.3 0.7)) }
        "done"    { $r.circle.Background = Brush "#1F7A52"; $r.circle.BorderBrush = Brush "#1F7A52"; $r.glyph.Text = [char]0xE73E; $r.name.Foreground = Brush "#ECECF1"; $r.name.FontWeight = "Normal" }
        "failed"  { $r.circle.Background = Brush "#C93030"; $r.circle.BorderBrush = Brush "#C93030"; $r.glyph.Text = [char]0xE711; $r.name.Foreground = Brush "#FF8A8A"; $r.name.FontWeight = "SemiBold" }
    }
}

$script:runner = $null; $script:logShown = 0; $script:shownFrac = 0.0
function Start-Install($from) {
    $sync.phase = "running"; $sync.cancel = $false; $sync.error = ""
    for ($i = $from; $i -lt $Steps.Count; $i++) { $sync.state[$i] = "pending" }
    $ui.Welcome.Visibility = "Collapsed"; $ui.Progress.Visibility = "Visible"
    $ui.ProgTitle.Text = "Installing Parlo"; $ui.ProgSub.Text = "This takes about 15 to 30 minutes, mostly downloading. You can keep using your PC."
    $ui.BtnRetry.Visibility = "Collapsed"; $ui.BtnClose2.Visibility = "Collapsed"; $ui.BtnStop.Visibility = "Visible"
    $ui.Fill.Background.GradientStops[0].Color = [Windows.Media.ColorConverter]::ConvertFromString("#E96B32")
    $ui.Fill.Background.GradientStops[1].Color = [Windows.Media.ColorConverter]::ConvertFromString("#C2410C")
    Start-Waveform
    $ps = [powershell]::Create()
    [void]$ps.AddScript($Worker).AddArgument($sync).AddArgument($Steps).AddArgument($Root).AddArgument([bool]$Preview).
        AddArgument([bool]$ui.OptDesktop.IsChecked).AddArgument([bool]$ui.OptStart.IsChecked).AddArgument($from)
    $script:runner = @{ ps = $ps; handle = $ps.BeginInvoke() }
}

# The window thread polls the shared state ten times a second.
$timer = New-Object Windows.Threading.DispatcherTimer; $timer.Interval = [TimeSpan]::FromMilliseconds(100)
$timer.Add_Tick({
    if ($sync.phase -eq "welcome") { return }
    $done = 0.0; $total = ($Steps | ForEach-Object { $_.weight } | Measure-Object -Sum).Sum
    for ($i = 0; $i -lt $Steps.Count; $i++) {
        Set-Row $i $sync.state[$i]
        if ($sync.state[$i] -eq "done") { $done += $Steps[$i].weight }
        $d = $sync.detail[$i]
        if ($i -eq $sync.current -and $sync.state[$i] -eq "active" -and $sync.frac -gt 0) { $d = "{0:P0}" -f $sync.frac }
        if ($sync.state[$i] -eq "failed") { $d = "failed" }
        $rows[$i].det.Text = $d
    }
    if ($sync.current -ge 0 -and $sync.current -lt $Steps.Count -and $sync.state[$sync.current] -eq "active") { $done += $Steps[$sync.current].weight * $sync.frac }
    $target = [math]::Min(1.0, $done / $total)
    $script:shownFrac += ($target - $script:shownFrac) * 0.25  # glide towards the real value
    $ui.Fill.Width = [math]::Max(0, ($ui.Track.ActualWidth) * $script:shownFrac)
    $ui.Pct.Text = "{0:P0}" -f $target
    $ui.Status.Text = $sync.status
    while ($script:logShown -lt $sync.log.Count) { $ui.LogBox.AppendText($sync.log[$script:logShown] + "`r`n"); $script:logShown++ }
    if ($ui.LogBox.Visibility -eq "Visible") { $ui.LogBox.ScrollToEnd() }
    if ($sync.phase -eq "done") {
        $sync.phase = "finished"; Stop-Waveform
        $ui.Progress.Visibility = "Collapsed"; $ui.Done.Visibility = "Visible"
        $ui.BadgeScale.BeginAnimation([Windows.Media.ScaleTransform]::ScaleXProperty, (Anim 0.3 1 0.35 $false))
        $ui.BadgeScale.BeginAnimation([Windows.Media.ScaleTransform]::ScaleYProperty, (Anim 0.3 1 0.35 $false))
    } elseif ($sync.phase -eq "failed") {
        $sync.phase = "stopped"; Stop-Waveform
        $ui.ProgTitle.Text = "Setup hit a problem"; $ui.ProgSub.Text = $sync.error
        $sync.status = "Fix the problem above, then press Try again."
        $ui.Status.Text = $sync.status
        $ui.Fill.Background.GradientStops[0].Color = [Windows.Media.ColorConverter]::ConvertFromString("#E05252")
        $ui.Fill.Background.GradientStops[1].Color = [Windows.Media.ColorConverter]::ConvertFromString("#C93030")
        $ui.BtnStop.Visibility = "Collapsed"; $ui.BtnRetry.Visibility = "Visible"; $ui.BtnClose2.Visibility = "Visible"
    }
})
$timer.Start()

function Confirm-Quit {
    if ($sync.phase -ne "running") { return $true }
    $r = [Windows.MessageBox]::Show($win, "Stop installing Parlo? You can run Setup again later; finished steps are kept.", "Parlo", "YesNo", "Question")
    if ($r -ne "Yes") { return $false }
    $sync.cancel = $true; if ($sync.proc) { try { $sync.proc.Kill() } catch {} }
    return $true
}
$ui.BtnInstall.Add_Click({ Start-Install 0 })
$ui.BtnCancel.Add_Click({ $win.Close() })
$ui.CloseX.Add_Click({ if (Confirm-Quit) { $win.Close() } })
$ui.BtnStop.Add_Click({ if (Confirm-Quit) { $win.Close() } })
$ui.BtnClose2.Add_Click({ $win.Close() })
$ui.BtnClose3.Add_Click({ $win.Close() })
$ui.BtnRetry.Add_Click({ $from = [array]::IndexOf($sync.state, "failed"); if ($from -lt 0) { $from = 0 }; Start-Install $from })
$ui.BtnDetails.Add_Click({
    $show = $ui.LogBox.Visibility -ne "Visible"
    $ui.LogBox.Visibility = if ($show) { "Visible" } else { "Collapsed" }
    $ui.StepList.Visibility = if ($show) { "Hidden" } else { "Visible" }
    $ui.BtnDetails.Content = if ($show) { "Show steps" } else { "Show details" }
})
$ui.BtnLaunch.Add_Click({
    if (-not $Preview) { Start-Process -FilePath (Join-Path $Root ".venv\Scripts\pythonw.exe") -ArgumentList "`"$Root\app\main.py`"" -WorkingDirectory $Root }
    $win.Close()
})

# -Snapshot: save each screen as a PNG (for checking the design), then close.
if ($Snapshot) {
    New-Item -ItemType Directory -Force $Snapshot | Out-Null
    function Save-Snap($name) {
        $el = $win; $w = [int]$win.ActualWidth; $h = [int]$win.ActualHeight
        $bmp = New-Object Windows.Media.Imaging.RenderTargetBitmap($w, $h, 96, 96, [Windows.Media.PixelFormats]::Pbgra32)
        $bmp.Render($el)
        $enc = New-Object Windows.Media.Imaging.PngBitmapEncoder; $enc.Frames.Add([Windows.Media.Imaging.BitmapFrame]::Create($bmp))
        $fs = [IO.File]::Create((Join-Path $Snapshot "$name.png")); $enc.Save($fs); $fs.Close()
    }
    $script:snapStage = 0
    $snapTimer = New-Object Windows.Threading.DispatcherTimer; $snapTimer.Interval = [TimeSpan]::FromMilliseconds(250)
    $snapTimer.Add_Tick({
        switch ($script:snapStage) {
            0 { Save-Snap "1-welcome"; $script:snapStage = 1
                if (-not $Preview) { $ui.OptDesktop.IsChecked = $false; $ui.OptStart.IsChecked = $false }  # test runs add no shortcuts
                Start-Install 0 }
            1 { if ($sync.current -ge 3 -and $sync.frac -ge 0.5) { Save-Snap "2-installing"; $script:snapStage = 2 } }
            2 { if ($sync.current -ge 3) { $ui.BtnDetails.RaiseEvent((New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent))); $script:snapStage = 3 } }
            3 { Save-Snap "3-details"; $ui.BtnDetails.RaiseEvent((New-Object Windows.RoutedEventArgs([Windows.Controls.Button]::ClickEvent))); $script:snapStage = 4 }
            4 { if ($sync.phase -eq "finished") { $script:snapStage = 5 } }
            5 { Save-Snap "4-done"; $script:snapStage = 6
                # also show the failure screen once
                $sync.state[6] = "failed"; $sync.state[7] = "pending"; $sync.detail[7] = ""
                $sync.error = "The AI writing model could not be downloaded. Check your internet connection."
                $ui.Done.Visibility = "Collapsed"; $ui.Progress.Visibility = "Visible"; $sync.phase = "failed" }
            6 { Save-Snap "5-failed"; $win.Close() }
        }
    })
    $win.Add_ContentRendered({ $snapTimer.Start() })
}

[void]$win.ShowDialog()
$timer.Stop()
if ($script:runner) { try { $sync.cancel = $true; $script:runner.ps.Stop() } catch {} }
