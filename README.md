# napari-workflows

[![License](https://img.shields.io/pypi/l/napari-workflows.svg?color=green)](https://github.com/haesleinhuepf/napari-workflows/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/napari-workflows.svg?color=green)](https://pypi.org/project/napari-workflows)
[![Python Version](https://img.shields.io/pypi/pyversions/napari-workflows.svg?color=green)](https://python.org)
[![tests](https://github.com/haesleinhuepf/napari-workflows/workflows/tests/badge.svg)](https://github.com/haesleinhuepf/napari-workflows/actions)
[![codecov](https://codecov.io/gh/haesleinhuepf/napari-workflows/branch/main/graph/badge.svg)](https://codecov.io/gh/haesleinhuepf/napari-workflows)
[![Development Status](https://img.shields.io/pypi/status/napari-workflows.svg)](https://en.wikipedia.org/wiki/Software_release_life_cycle#Alpha)

This repository contains data structures for managing image processing workflows in napari. 
There are no user interface in this repository as it serves as backend. 
Multiple front-ends managing the workflows are available in these napari plugins:
* [napari_pyclesperanto_assistant](https://github.com/clesperanto/napari_pyclesperanto_assistant)
* [napari-workflow-optimizer](https://github.com/haesleinhuepf/napari-workflow-optimizer)
* [napari-workflow-inspector](https://github.com/haesleinhuepf/napari-workflow-inspector)

If you want to learn how these workflows function under the hood, the 
[demo notebook](https://github.com/haesleinhuepf/napari-workflows/blob/main/docs/demo.ipynb) 
gives some insights. A public API for extending these workflows with custom functions and other
napari plugins will be published in spring 2022. Stay tuned.

----------------------------------

This repository was generated with [Cookiecutter] using [@napari]'s [cookiecutter-napari-plugin] template.

## Installation

You can install `napari-workflows` via [pip]:

    pip install napari-workflows

## Contributing

Contributions are very welcome. Tests can be run with [tox], please ensure
the coverage at least stays the same before you submit a pull request.

## License

Distributed under the terms of the [BSD-3] license,
"napari-workflows" is free and open source software

## Issues

If you encounter any problems, please [file an issue] along with a detailed description.

[napari]: https://github.com/napari/napari
[Cookiecutter]: https://github.com/audreyr/cookiecutter
[@napari]: https://github.com/napari
[MIT]: http://opensource.org/licenses/MIT
[BSD-3]: http://opensource.org/licenses/BSD-3-Clause
[GNU GPL v3.0]: http://www.gnu.org/licenses/gpl-3.0.txt
[GNU LGPL v3.0]: http://www.gnu.org/licenses/lgpl-3.0.txt
[Apache Software License 2.0]: http://www.apache.org/licenses/LICENSE-2.0
[Mozilla Public License 2.0]: https://www.mozilla.org/media/MPL/2.0/index.txt
[cookiecutter-napari-plugin]: https://github.com/napari/cookiecutter-napari-plugin

[file an issue]: https://github.com/haesleinhuepf/napari-workflows/issues

[napari]: https://github.com/napari/napari
[tox]: https://tox.readthedocs.io/en/latest/
[pip]: https://pypi.org/project/pip/
[PyPI]: https://pypi.org/
