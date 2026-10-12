from templates.v2.schema import get_template_schema, reconcile_schema_limits


def test_contradictory_limits_become_satisfiable():
    schema = {
        "type": "object",
        "properties": {
            "heading": {"type": "string", "minLength": 27, "maxLength": 25},
            "fine": {"type": "string", "minLength": 5, "maxLength": 40},
            "bullets": {
                "type": "array",
                "minItems": 5,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 90, "maxLength": 60},
            },
            "value": {"type": "number", "minimum": 10, "maximum": 2},
        },
    }
    reconcile_schema_limits(schema)
    properties = schema["properties"]
    assert properties["heading"] == {"type": "string", "minLength": 13, "maxLength": 25}
    assert properties["fine"] == {"type": "string", "minLength": 5, "maxLength": 40}
    assert properties["bullets"]["minItems"] == 3
    assert properties["bullets"]["items"]["minLength"] == 30
    assert properties["value"]["minimum"] == 2


def test_template_schema_never_asks_for_impossible_text():
    # Shape of an imported layout whose heading had min_length 27 > max_length 25.
    template = {
        "layouts": [
            {
                "id": "title_cards_footer_layout",
                "description": "Header above cards",
                "components": [
                    {
                        "id": "header",
                        "description": "Heading",
                        "elements": [
                            {
                                "type": "text",
                                "decorative": False,
                                "name": "main_heading_start",
                                "min_length": 27,
                                "max_length": 25,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    schema = get_template_schema(template)["layouts"][0]["schema"]
    heading = schema["properties"]["header"]["properties"]["main_heading_start"]
    assert heading["minLength"] <= heading["maxLength"] == 25
