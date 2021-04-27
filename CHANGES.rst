.. currentmodule:: flask-pydantic-spec

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