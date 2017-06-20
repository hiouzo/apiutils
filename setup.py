import apiutils
from setuptools import setup

setup(
    name='apiutils',
    description='API Utlities.',
    version=apiutils.__version__,
    url='N/A',
    author='ycyuxin',
    author_email='ycyuxin(at)qq.com',
    packages=['apiutils'],
    package_data={
        'apiutils': ['postman/schema*.json']
    },
    entry_points={
        'console_scripts':
            [
                'apicapture = apiutils.apicapture:run',
                'apiview = apiutils.apiview:run',
                'apiswagger = apiutils.apiswagger:run',
                'apischema = apiutils.apischema:run',
                'apiblue = apiutils.apiblue:run',
                'apiman = apiutils.apiman:run',
                'apigen = apiutils.apigen:run',
            ]
    },
    install_requires=[
        'click',
        'genson',
        'jsonschema',
        'openapi',
        'PyYAML',
        'pyaml',
    ],
    zip_safe=False
)
