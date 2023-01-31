.. Flask-Pydantic-Spec documentation master file, created by
   sphinx-quickstart on Sun Dec  1 16:11:49 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Flask-Pydantic-Spec's documentation!
====================================

|GitHub Actions| |pypi| |versions| |Language grade: Python|
|Documentation Status|

Yet another library to generate OpenAPI document and validate request &
response with Python annotations.

Features
--------

-  Less boilerplate code, annotations are really easy-to-use
-  Generate API document with `Redoc UI`_ or `Swagger UI`_
-  Validate query, JSON data, response data with `pydantic`_
-  Current support:

   -  Flask

Quick Start
-----------

install with pip: ``pip install flask_pydantic_openapi``

Examples
~~~~~~~~

Check the `examples`_ folder.

Step by Step
~~~~~~~~~~~~

1. Define your data structure used in (query, json, headers, cookies,
   resp) with ``pydantic.BaseModel``
2. create ``flask_pydantic_openapi.Validator`` instance with the web framework name you
   are using, like ``api = Validator('flask')``
3. ``api.validate`` decorate the route with

   -  ``query``
   -  ``json``
   -  ``headers``
   -  ``cookies``
   -  ``resp``
   -  ``tags``

4. access these data with ``context(query, json, headers, cookies)`` (of
   course, you can access these from the original place where the
   framework offered)

   -  flask: ``request.context``
   -  falcon: ``req.context``
   -  starlette: ``request.context``

5. register to the web application ``api.register(app)``
6. check the document at URL location ``/apidoc/redoc`` or
   ``/apidoc/swagger``

FAQ
---

   ValidationError: missing field for headers

The HTTP headers’ keys in Flask are capitalized

.. _Redoc UI: https://github.com/Redocly/redoc
.. _Swagger UI: https://github.com/swagger-api/swagger-ui
.. _pydantic: https://github.com/samuelcolvin/pydantic/

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   flask_backend
   config
   utils
   types
   spec



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
