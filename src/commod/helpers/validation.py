import logging

logger = logging.getLogger("dem")

def validate_dict(validating_dict: dict, scheme: dict) -> bool:
    """Validate dictionary based on scheme.

    Supported scheme formats:
    {name: [list of possible types, required(bool)]}.
    Supports generics for type checking in schemes
    """
    # logger.debug(f"Validating dict with scheme {scheme.keys()}")
    if not isinstance(validating_dict, dict):
        logger.error(f"Validated part of scheme is not a dict: {validating_dict}")
        return False
    for field, field_scheme in scheme.items():
        types = field_scheme[0]
        required = field_scheme[1]
        value = validating_dict.get(field)
        if required and value is None:
            logger.error(f"key '{field}' is required but couldn't be found in manifest")
            return False

        if required or (not required and value is not None):
            generics_present = any([hasattr(type_entry, "__origin__") for type_entry in types])
            if not generics_present:
                valid_type = any([isinstance(value, type_entry) for type_entry in types])
            else:
                valid_type = True
                for type_entry in types:
                    if (hasattr(type_entry, "__origin__")
                       and isinstance(value, typing.get_origin(type_entry))):
                        if type(value) in [dict, list]:
                            for value_internal in value:
                                if not isinstance(value_internal, typing.get_args(type_entry)):
                                    valid_type = False
                                    break
                        else:
                            valid_type = False
                            break

            if not valid_type:
                logger.error(f"key '{field}' has value {value} of invalid type '{type(value)}', "
                             f"expected: {' or '.join(str(type_inst) for type_inst in types)}")
                return False
    return True

def validate_dict_constrained(validating_dict: dict, scheme: dict) -> bool:
        """Validate dictionary based on scheme.

        Supported scheme format:
        {name: [list of possible types, required(bool), int or float value[min, max]]}.
        Doesn't support generics in schemes.
        """
        # logger.debug(f"Validating constrained dict with scheme {scheme.keys()}")
        for field, field_scheme in scheme.items():
            types = field_scheme[0]
            required = field_scheme[1]
            value = validating_dict.get(field)
            if (float in types) or (int in types):
                min_req = field_scheme[2][0]
                max_req = field_scheme[2][1]

            if required and value is None:
                logger.error(f"key '{field}' is required but couldn't be found in manifest")
                return False

            if required or (not required and value is not None):
                valid_type = any(isinstance(value, type_entry) for type_entry in types)
                if not valid_type:
                    logger.error(f"key '{field}' is of invalid type '{type(field)}', expected '{types}'")
                    return False
                if float in types:
                    try:
                        value = float(value)
                    except ValueError:
                        logger.error(f"key '{field}' can't be converted to float as supported - "
                                     f"found value '{value}'")
                        return False
                if int in types:
                    try:
                        value = int(value)
                    except ValueError:
                        logger.error(f"key '{field}' can't be converted to int as supported - "
                                     f"found value '{value}'")
                        return False
                if ((float in types) or (int in types)) and (not (min_req <= value <= max_req)):
                    logger.error(f"key '{field}' is not in supported range '{min_req}-{max_req}'")
                    return False

        return True

def validate_list(validating_list: list[dict], scheme: dict) -> bool:
    """Run validate_dict for multiple lists with the same scheme.

    Return total validation result for them
    """
    to_validate = [element for element in validating_list if isinstance(element, dict)]
    return all(validate_dict(element, scheme) for element in to_validate)