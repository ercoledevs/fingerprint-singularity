"""Compare support/v3 Python and Rust, including Python-object conversion.

Run after installing ./server/native: python scripts/benchmark-native.py
This is a CPU microbenchmark, not an HTTP/database throughput measurement.
"""
import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))

from singularity import native, resilient_kernel  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=1000)
    parser.add_argument('--warmups', type=int, default=100)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts/native/performance.json')
    args = parser.parse_args()
    if args.samples < 20 or args.warmups < 0:
        parser.error('Use at least 20 samples and nonnegative warmups')
    if native.BACKEND != 'rust':
        parser.error('Rust kernel unavailable or disabled; install ./server/native and use SINGULARITY_KERNEL=rust')
    snapshot = dict(schema='singularity/v3', scope='benchmark', probe='web/v2', engine='blink',
                    signals=dict(platform='macos', cores=8, memory=8, language='en', timezone='UTC'),
                    detail=dict(gpu='a' * 64, fonts='b' * 64, canvas='c' * 64))
    functions = dict(python=resilient_kernel.match_python, rust=resilient_kernel.match)
    rows = []
    for scenario in ('identical-contenders', 'unique-winner'):
        for count in (1, 16, 64, 256):
            candidates = []
            for i in range(count):
                other = {**snapshot, 'signals': dict(snapshot['signals']), 'detail': dict(snapshot['detail'])}
                if scenario == 'unique-winner' and i:
                    other['detail']['gpu'] = 'd' * 64
                candidates.append(dict(id=f'candidate-{i}', snapshot=other))
            assert functions['python'](snapshot, candidates) == functions['rust'](snapshot, candidates)
            for _ in range(args.warmups):
                for call in functions.values():
                    call(snapshot, candidates)
            samples = {name: [] for name in functions}
            for i in range(args.samples):
                # Alternate order to reduce systematic scheduling/thermal bias.
                for name in (('python', 'rust') if i % 2 == 0 else ('rust', 'python')):
                    start = time.perf_counter_ns()
                    functions[name](snapshot, candidates)
                    samples[name].append((time.perf_counter_ns() - start) / 1_000_000)
            row = dict(scenario=scenario, count=count)
            for name, times in samples.items():
                times.sort()
                row[name] = dict(p50Ms=statistics.median(times), p95Ms=times[int(len(times) * 0.95)],
                                 p99Ms=times[int(len(times) * 0.99)])
            row['medianSpeedup'] = row['python']['p50Ms'] / row['rust']['p50Ms']
            rows.append(row)
    report = dict(python=platform.python_version(), machine=platform.machine(), platform=platform.platform(),
                  backend=native.BACKEND, samples=args.samples, warmups=args.warmups, rows=rows,
                  note='Current support/v3, release Rust build; validation, matching, FFI and result allocation included. '
                       'No HTTP, MongoDB, lock contention, production throughput or browser acceleration measured.')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('scenario                 candidates  Python p50   Rust p50   speedup')
    for row in rows:
        print(f"{row['scenario']:24} {row['count']:10}  {row['python']['p50Ms']:9.4f}ms "
              f"{row['rust']['p50Ms']:8.4f}ms {row['medianSpeedup']:7.2f}x")
    print(f'Evidence: {args.out}')


if __name__ == '__main__':
    main()
