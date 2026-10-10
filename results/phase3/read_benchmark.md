# Read-Strategy Benchmark (Phase 3, Part 3.0)

Scenes benchmarked: 2

## Strategy (a): fetch-to-staging

- Avg wall time: 3.96 s
- Avg bytes transferred: 606.3 MB
- Avg request count: 1.0
- Avg peak staging disk: 606.3 MB

## Strategy (b): direct remote windowed read (/vsizip/vsis3/)

- Avg wall time: 1.39 s
- Avg bytes transferred: 8.89 MB
- Avg request count: 43.0
- Avg peak staging disk: 0.0 MB

## Per-scene detail

- `vizag-geoai/data/raw/sentinel2/2018/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013.SAFE.zip`: (a) 5.85s / 885.3 MB / 1 req vs (b) 1.87s / 9.63 MB / 53 req
- `vizag-geoai/data/raw/sentinel2/2018/S2A_MSIL2A_20180116T050121_N0500_R119_T44QQE_20230824T005439.SAFE.zip`: (a) 2.07s / 327.2 MB / 1 req vs (b) 0.92s / 8.14 MB / 33 req