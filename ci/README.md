# Bounded offline CI

This job qualifies only Python 3.12, Heat 27.0.0 and cloudsigma 3.0.0rc1.
It does not expand the SDK's reviewed Python >=3.10,<3.13 policy or qualify
other Python versions allowed by this experimental Heat package's metadata.

cloudsigma 3.0.0rc1 is not available on PyPI (metadata lookup returned 404).
CI therefore explicitly builds the official reviewed SDK source at
296e21e9c0f0ec205d839b1d3c6fa22e674f18df. This is not a release claim.
Its isolated build uses its own exact setuptools 75.3.2 / wheel 0.45.1 pins;
the Heat wheel uses the retained setuptools 84.0.0 closure. constraints.txt
pins the retained qualification distribution inventory, not floating upgrades.
Public metadata for every pin was checked when preparing this workflow.

Dependency acquisition/build is allowed to use public GitHub/PyPI. The test
processes get an empty environment except explicit synthetic configuration,
a disposable HOME/cwd, and -I -B. Each test installs its socket/process audit
guard before third-party imports; only fake HTTP and disposable local SQLite
are used. No credentials, cloud endpoints or cloud resource calls are used.
This is an accidental-effects guard, not a sandbox for malicious Python code.

The unchanged three installed-contract methods and retained 42 reviewer refusal
probes run against the installed wheel. verify_wheel.py separately compares
source, wheel members and installed module hashes, excludes test/CI code and
auto-registration, and checks LICENSE retention. No whole Heat engine, worker
restart, distributed recovery, operational authorization or live behavior is
claimed. Historical README/plugin/license and experimental implementation are
unchanged. Hosted install/pip-check and test success remain required before merge.
