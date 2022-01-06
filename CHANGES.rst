.. currentmodule:: flask-pydantic-spec

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
