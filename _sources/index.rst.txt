Venv-Pack
==========

``venv-pack`` is a command-line tool for packaging `virtual environments
<https://docs.python.org/3/library/venv.html>`__ for distribution. This is
useful for deploying code in a consistent environment.

Supports virtual environments created using:

- `venv <https://docs.python.org/3/library/venv.html>`__ (part of the standard
  library, preferred method)
- `virtualenv <https://virtualenv.pypa.io/en/stable/>`__ (older tool, Python 2
  compatible)

See `conda-pack <https://conda.github.io/conda-pack/>`__ for a similar tool
made for `Conda environments <http://conda.io/>`__.


.. raw:: html

    <div align="center">
      <script src="https://asciinema.org/a/197783.js" id="asciicast-197783" async data-speed="2"></script>
    </div>


Installation
------------

**Install from Conda-Forge:**

.. code-block:: bash

    $ conda install -c conda-forge venv-pack


**Install from PyPI:**

.. code-block:: bash

    $ pip install venv-pack


**Install from source:**

``venv-pack`` is `available on github <https://github.com/jcrist/venv-pack>`__
and can always be installed from source.

.. code-block:: bash

    $ pip install git+https://github.com/jcrist/venv-pack.git


Command-line Usage
-----------------

``venv-pack`` is primarily a command-line tool. Full CLI docs can be found
:doc:`here <cli>`.

One common use case is packing an environment on one machine to distribute to
other machines as part of a deployment process.

On the source machine

.. code-block:: bash

    # Pack the current environment into my_env.tar.gz
    $ venv-pack -o my_env.tar.gz

    # Pack an environment located at an explicit path into my_env.tar.gz
    $ venv-pack -p /explicit/path/to/my_env

On the target machine

.. code-block:: bash

    # Unpack environment into directory `my_env`
    $ mkdir -p my_env
    $ tar -xzf my_env.tar.gz -C my_env

    # Use python without activating the environment. Most python
    # libraries will work fine, but scripts (e.g. ipython) will fail.
    $ ./my_env/bin/python

    # Activate the environment. This adds `my_env/bin` to your path
    $ source my_env/bin/activate

    # Run python from in the environment
    (my_env) $ python

    # Scripts now work fine
    (my_env) $ ipython --version

    # Deactivate the environment to remove it from your path
    (my_env) $ deactivate


API Usage
---------

``venv-pack`` also provides a Python API, the full documentation of which can
be found :doc:`here <api>`. The API mostly mirrors that of the ``venv-pack``
command-line. Repeating the examples from above:

.. code-block:: python

    import venv_pack

    # Pack the current environment into my_env.tar.gz
    venv_pack.pack(output='my_env.tar.gz')

    # Pack an environment located at an explicit path into my_env.tar.gz
    venv_pack.pack(prefix="/explicit/path/to/my_env")


Caveats
-------

This tool is new, and has a few caveats.

- Python is *not* packaged with the environment, but rather symlinked in the
  environment. This is useful for deployment situations where Python is already
  installed on the machine, but the required library dependencies may not be.

- Windows is not currently supported (should be easy to fix, contributions
  welcome!)

- The os *type* where the environment was built must match the os *type* of the
  target. This means that environments built on windows can't be relocated to
  linux.


.. toctree::
    :hidden:

    api.rst
    cli.rst
    spark.rst
