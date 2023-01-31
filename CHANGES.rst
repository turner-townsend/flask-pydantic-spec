.. currentmodule:: flask-pydantic-openapi
VERSION 0.4.2
-------------

Release 2023-01-31

- Add ability to add root path to config to add additional prefix in api routes
- Add ability to hide openapi docs


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
