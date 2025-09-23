Param(
  [string]$AlphaList = "0.55,0.65,0.70,0.75",
  [string]$K1List = "1.4,1.6,1.8",
  [string]$BList = "0.6,0.7,0.8",
  [int]$TopK = 6,
  [int]$WarmPasses = 2
)

function Run-Eval {
  param([string]$Alpha, [string]$K1, [string]$B, [int]$TopK, [int]$Passes)

  $env:FUSION_ALPHA = $Alpha
  $env:BM25_K1 = $K1
  $env:BM25_B = $B
  $env:TOP_K = "$TopK"

  for ($i=0; $i -lt $Passes; $i++) {
    Write-Host ">>> Eval pass $($i+1) :: α=$Alpha K1=$K1 B=$B TOP_K=$TopK"
    make eval
  }
}

# Baseline: assume default α/K1/B/TOP_K in env/config
Write-Host ">>> Running warm baseline x$WarmPasses"
for ($i=0; $i -lt $WarmPasses; $i++) { make eval }

# Fusion sweep (BM25 held constant by your defaults)
$alphas = $AlphaList.Split(",")
foreach ($a in $alphas) {
  Run-Eval -Alpha $a.Trim() -K1 $env:BM25_K1 -B $env:BM25_B -TopK $TopK -Passes $WarmPasses
}

# BM25 sweep with the best α (set it before calling or re-run with -AlphaList "BEST")
$bestAlpha = $env:FUSION_ALPHA
$k1s = $K1List.Split(",")
$bs = $BList.Split(",")
foreach ($k1 in $k1s) {
  foreach ($b in $bs) {
    Run-Eval -Alpha $bestAlpha -K1 $k1.Trim() -B $b.Trim() -TopK $TopK -Passes $WarmPasses
  }
}

Write-Host ">>> Optional TOP_K probes (4 & 8) with current α/K1/B"
Run-Eval -Alpha $env:FUSION_ALPHA -K1 $env:BM25_K1 -B $env:BM25_B -TopK 4 -Passes $WarmPasses
Run-Eval -Alpha $env:FUSION_ALPHA -K1 $env:BM25_K1 -B $env:BM25_B -TopK 8 -Passes $WarmPasses

Write-Host "All sweeps done. Inspect logs/metrics.csv and update docs/tuning-report-week4.md."
