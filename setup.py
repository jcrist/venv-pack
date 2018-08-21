from setuptools import setup
import versioneer

setup(name='venv-pack',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      url='https://jcrist.github.io/venv-pack/',
      project_urls={"Source Code": "https://github.com/jcrist/venv-pack/"},
      maintainer='Jim Crist',
      maintainer_email='jiminy.crist@gmail.com',
      keywords='venv packaging',
      classifiers=["Development Status :: 4 - Beta",
                   "License :: OSI Approved :: BSD License",
                   "Programming Language :: Python :: 2.7",
                   "Programming Language :: Python :: 3.5",
                   "Programming Language :: Python :: 3.6",
                   "Programming Language :: Python :: 3.7",
                   "Topic :: System :: Archiving :: Packaging",
                   "Topic :: System :: Software Distribution",
                   "Topic :: Software Development :: Build Tools"],
      license='BSD',
      description='Package virtual environments for redistribution',
      long_description=open('README.rst').read(),
      packages=['venv_pack'],
      package_data={'venv_pack': ['scripts/*',
                                  'scripts/common/*']},
      entry_points='''
        [console_scripts]
        venv-pack=venv_pack.__main__:main
      ''',
      zip_safe=False)
