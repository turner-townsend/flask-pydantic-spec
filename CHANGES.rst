.. currentmodule:: flask-pydantic-spec

VERSION 0.7.0
------------

Release 2025-04-09

- Drop support for Python 3.8
- Add support for Pydantic V2 and drop support for Pydantic V1
- Fix typo in flask_pydantic_spec/types.py


VERSION 0.6.0
-------------

Release 2024-01-12

- Add ability to parse binary JSON encoded parts of multipart/form-data requests


VERSION 0.5.0
-------------

Release 2023-09-28

- Drop support for Python 3.7
- Add support for Python list in Response
- Add support for custom URL converters


VERSION 0.4.5
-------------

Release 2023-04-24

- Generate Multipart-form request schema data correctly


VERSION 0.4.4
-------------

Release 2023-04-17

- Handle JSON requests with an empty body - thanks @TheForgottened
- Handle missing definition key when cleaning up schemas


VERSION 0.4.3
-------------

Release 2023-03-13

- Use Pydantic functionality to generate valid OpenAPI spec and fix issue with custom `__root__` models.

VERSION 0.4.2
-------------

Release 2023-02-20

- Remove `nested-alter` dependency and replicate behaviour in the library to avoid potential build issues


VERSION 0.4.1
-------------

Release 2022-11-14

- Add ability to parse nested multipart form requests with JSON strings under keys


VERSION 0.4.0
-------------

Release 2022-11-14

- Drop support for Python 3.6

VERSION 0.3.1
-------------

Release 2022-03-07

- Add ability to correctly parse and validate gzipped requests


VERSION 0.3.0
-------------

Release 2022-02-1

- Fix logic when adding a model to multipart/form-data requests


Version 0.2.1
-------------

Release 2022-01-11

- Relax restrictions on content-type when checking for "application/json".

Version 0.2.0
-------------

Release 2022-01-06

- Relax pip dependency versions

Version 0.1.5
-------------

Released 2021-07-29

- Fixed a bug where a model added to a query that contained a reference to another model would not get added to the OpenAPI document correctly.


Version 0.1.4
-------------

Released 2021-04-27

- Added the ability to specify multiple query params with the same name and for these to be interpreted as a list in the pydantic model that is used

Version 0.1.3
-------------

Released 2020-11-23

- Allowed the validation to handle optional parameters (i.e the body of a request is Optional)


Version 0.1.2
-------------

Released 2020-11-23

- Added type hints and MyPy linting throughout the code base.
- Removed references to Spectree
- Removed any other backend other than the Flask one.
- Major refactoring and cleanup
