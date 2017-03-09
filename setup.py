from setuptools import setup

setup(name='py-xml-escpos',
      version='0.1',
      description='Print ESC/POS using xml',
      #url='http://github.com/storborg/funniest',
      author='Renato Lorenzi',
      author_email='renato.lorenzi@hotmail.com',
      license='MIT',
      packages=['xml_escpos'],
      install_requires=['python-escpos'],
      zip_safe=False)