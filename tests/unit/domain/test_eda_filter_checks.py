from __future__ import annotations

from veupathdb.domain.eda_validation import validate_filters

from ._eda_facts import (
    GENE_PHENOTYPE,
    BareFilt,
    Ent,
    Filt,
    Study,
    Sub,
    Var,
    phenotype_study,
)

_ENT = GENE_PHENOTYPE
_SUCCESS = "VAR_a8ad31c0"
_COUNT = "EUPATH_0043064"
_DATE = "EUPATH_0043256"


def _errors(*filters: Filt | BareFilt) -> list[str]:
    return validate_filters(phenotype_study(), list(filters))


def test_a_valid_string_set_produces_no_errors() -> None:
    assert _errors(Filt(_ENT, _SUCCESS, "stringSet", string_set=["yes"])) == []


def test_an_unknown_entity_is_reported_with_its_id() -> None:
    errors = _errors(Filt("ENT_nope", "V", "stringSet", string_set=["x"]))
    assert len(errors) == 1
    assert "ENT_nope" in errors[0]


def test_an_unknown_variable_is_reported_with_its_id() -> None:
    errors = _errors(Filt(_ENT, "VAR_deadbeef", "stringSet", string_set=["x"]))
    assert len(errors) == 1
    assert "VAR_deadbeef" in errors[0]


def test_a_string_set_on_a_number_variable_names_the_expected_type() -> None:
    errors = _errors(Filt(_ENT, _COUNT, "stringSet", string_set=["1"]))
    assert len(errors) == 1
    assert "integer" in errors[0]
    assert "stringSet" in errors[0]


def test_a_string_set_on_a_category_variable_is_refused() -> None:
    assert len(_errors(Filt(_ENT, "CAT_1", "stringSet", string_set=["Yes"]))) == 1


def test_an_out_of_vocabulary_value_is_the_error_the_service_will_not_give() -> None:
    """Live this returns 200 with count 0, so this predicate is the only guard."""
    errors = _errors(Filt(_ENT, _SUCCESS, "stringSet", string_set=["maybe"]))
    assert len(errors) == 1
    assert "maybe" in errors[0]
    assert "no" in errors[0]
    assert "yes" in errors[0]


def test_an_empty_string_set_is_refused() -> None:
    assert len(_errors(Filt(_ENT, _SUCCESS, "stringSet", string_set=[]))) == 1


def test_an_unknown_filter_type_names_the_seven_that_exist() -> None:
    """stringPrefixSet is schema-present and wire-absent; the service answers 422."""
    errors = _errors(Filt(_ENT, _SUCCESS, "stringPrefixSet"))
    assert len(errors) == 1
    assert "stringPrefixSet" in errors[0]
    assert "stringSet" in errors[0]
    assert "multiFilter" in errors[0]


def test_a_number_set_on_an_integer_variable_refuses_a_fractional_member() -> None:
    errors = _errors(Filt(_ENT, _COUNT, "numberSet", number_set=[60.5]))
    assert len(errors) == 1
    assert "60.5" in errors[0]


def test_a_number_set_of_whole_numbers_passes() -> None:
    assert _errors(Filt(_ENT, _COUNT, "numberSet", number_set=[60.0, 61.0])) == []


def test_a_date_set_member_without_a_time_is_refused() -> None:
    errors = _errors(
        Filt(_ENT, _DATE, "dateSet", date_set=["2017-05-05T00:00:00", "2017-05-11"])
    )
    assert len(errors) == 1
    assert "T00:00:00" in errors[0]


def test_a_number_set_on_a_string_variable_is_refused() -> None:
    assert _errors(Filt(_ENT, _SUCCESS, "numberSet", number_set=[1.0])) == [
        (
            f"Filter numberSet on variable {_SUCCESS} of entity {_ENT} is refused: the "
            f"variable type is string, and numberSet applies to a variable of type "
            f"integer, number."
        )
    ]


def test_a_date_set_on_a_number_variable_is_refused() -> None:
    assert _errors(Filt(_ENT, _COUNT, "dateSet", date_set=["2017-05-05T00:00:00"])) == [
        (
            f"Filter dateSet on variable {_COUNT} of entity {_ENT} is refused: the "
            f"variable type is integer, and dateSet applies to a variable of type date."
        )
    ]


def test_a_string_variable_with_no_vocabulary_accepts_any_value() -> None:
    study = Study(
        id="STUDY_53f554ec6a",
        root_entity=Ent(id="E", variables=[Var(id="FREE_TEXT")]),
    )
    filters = [Filt("E", "FREE_TEXT", "stringSet", string_set=["anything"])]
    assert validate_filters(study, filters) == []


def test_a_fractional_member_passes_on_a_number_variable() -> None:
    study = Study(
        id="STUDY_53f554ec6a",
        root_entity=Ent(id="E", variables=[Var(id="RATE", type="number")]),
    )
    filters = [Filt("E", "RATE", "numberSet", number_set=[21.92])]
    assert validate_filters(study, filters) == []


def test_a_long_vocabulary_is_truncated_in_the_rejection() -> None:
    """The vocabulary reaches the model as retry text, so it cannot be unbounded."""
    study = Study(
        id="STUDY_53f554ec6a",
        root_entity=Ent(
            id="E",
            variables=[
                Var(id="GENE", vocabulary=[f"PF3D7_{index:04d}" for index in range(25)])
            ],
        ),
    )
    errors = validate_filters(
        study, [Filt("E", "GENE", "stringSet", string_set=["PF3D7_9999"])]
    )
    assert len(errors) == 1
    assert "PF3D7_0019" in errors[0]
    assert "PF3D7_0020" not in errors[0]
    assert "and 5 more" in errors[0]


class TestMultiFilter:
    def test_a_multifilter_on_a_non_multifilter_variable_is_refused(self) -> None:
        errors = _errors(
            Filt(
                _ENT,
                _SUCCESS,
                "multiFilter",
                sub_filters=[Sub(variable_id="CHILD_1", string_set=["Yes"])],
            )
        )
        assert len(errors) == 1
        assert "multifilter" in errors[0]

    def test_a_multifilter_sub_filter_must_be_a_child_of_the_category(self) -> None:
        errors = _errors(
            Filt(
                _ENT,
                "CAT_1",
                "multiFilter",
                sub_filters=[Sub(variable_id=_SUCCESS, string_set=["yes"])],
            )
        )
        assert len(errors) == 1
        assert _SUCCESS in errors[0]

    def test_a_well_formed_multifilter_passes(self) -> None:
        assert (
            _errors(
                Filt(
                    _ENT,
                    "CAT_1",
                    "multiFilter",
                    sub_filters=[Sub(variable_id="CHILD_1", string_set=["Yes"])],
                )
            )
            == []
        )

    def test_a_category_variable_without_the_multifilter_display_is_refused(
        self,
    ) -> None:
        study = Study(
            id="STUDY_53f554ec6a",
            root_entity=Ent(
                id="E",
                variables=[
                    Var(id="CAT_2", type="category", display_name="Plain group"),
                    Var(id="CHILD_2", parent_id="CAT_2", vocabulary=["Yes"]),
                ],
            ),
        )
        errors = validate_filters(
            study,
            [
                Filt(
                    "E",
                    "CAT_2",
                    "multiFilter",
                    sub_filters=[Sub(variable_id="CHILD_2", string_set=["Yes"])],
                )
            ],
        )
        assert len(errors) == 1
        assert "multifilter" in errors[0]
        assert "default" in errors[0]

    def test_a_multifilter_operation_outside_the_two_the_service_knows_is_refused(
        self,
    ) -> None:
        errors = _errors(
            Filt(
                _ENT,
                "CAT_1",
                "multiFilter",
                operation="xor",
                sub_filters=[Sub(variable_id="CHILD_1", string_set=["Yes"])],
            )
        )
        assert len(errors) == 1
        assert "xor" in errors[0]
        assert "union" in errors[0]
        assert "intersect" in errors[0]

    def test_a_sub_filter_with_no_members_is_refused(self) -> None:
        errors = _errors(
            Filt(_ENT, "CAT_1", "multiFilter", sub_filters=[Sub(variable_id="CHILD_1")])
        )
        assert len(errors) == 1
        assert "CHILD_1" in errors[0]

    def test_a_sub_filter_value_outside_the_child_vocabulary_is_refused(self) -> None:
        errors = _errors(
            Filt(
                _ENT,
                "CAT_1",
                "multiFilter",
                sub_filters=[Sub(variable_id="CHILD_1", string_set=["No"])],
            )
        )
        assert len(errors) == 1
        assert "No" in errors[0]
        assert "Yes" in errors[0]

    def test_every_bad_sub_filter_is_reported(self) -> None:
        errors = _errors(
            Filt(
                _ENT,
                "CAT_1",
                "multiFilter",
                sub_filters=[
                    Sub(variable_id="CHILD_1", string_set=["No"]),
                    Sub(variable_id="VAR_deadbeef", string_set=["Yes"]),
                ],
            )
        )
        assert len(errors) == 2


class TestAcrossFilters:
    def test_two_disjoint_sets_on_one_single_valued_variable_are_refused(self) -> None:
        """The most likely way to silently produce nothing: 200 with count 0."""
        errors = _errors(
            Filt(_ENT, _SUCCESS, "stringSet", string_set=["yes"]),
            Filt(_ENT, _SUCCESS, "stringSet", string_set=["no"]),
        )
        assert len(errors) == 1
        assert "one filter" in errors[0]

    def test_two_overlapping_sets_on_one_single_valued_variable_pass(self) -> None:
        """Overlapping sets narrow to the shared members, which is a real subset."""
        assert (
            _errors(
                Filt(_ENT, _SUCCESS, "stringSet", string_set=["yes", "no"]),
                Filt(_ENT, _SUCCESS, "stringSet", string_set=["yes"]),
            )
            == []
        )

    def test_two_disjoint_sets_on_a_multi_valued_variable_pass(self) -> None:
        study = Study(
            id="STUDY_53f554ec6a",
            root_entity=Ent(
                id="E",
                variables=[
                    Var(
                        id="VAR_035294d0",
                        vocabulary=["P. berghei", "P. falciparum"],
                        is_multi_valued=True,
                    )
                ],
            ),
        )
        assert (
            validate_filters(
                study,
                [
                    Filt("E", "VAR_035294d0", "stringSet", string_set=["P. berghei"]),
                    Filt(
                        "E", "VAR_035294d0", "stringSet", string_set=["P. falciparum"]
                    ),
                ],
            )
            == []
        )

    def test_every_error_is_reported_not_just_the_first(self) -> None:
        errors = _errors(
            Filt("ENT_nope", "V", "stringSet", string_set=["x"]),
            Filt(_ENT, _SUCCESS, "stringSet", string_set=["maybe"]),
        )
        assert len(errors) == 2


def test_a_filter_that_carries_no_payload_is_refused_for_every_type() -> None:
    """An omitted payload key is the same 400 as an empty one."""
    bare = [
        BareFilt(_ENT, _SUCCESS, "stringSet"),
        BareFilt(_ENT, _COUNT, "numberSet"),
        BareFilt(_ENT, _DATE, "dateSet"),
        BareFilt(_ENT, _COUNT, "numberRange"),
        BareFilt(_ENT, _DATE, "dateRange"),
        BareFilt(_ENT, "OBI_0001621", "longitudeRange"),
        BareFilt(_ENT, "CAT_1", "multiFilter"),
    ]
    for entry in bare:
        errors = _errors(entry)
        assert len(errors) == 1, entry.type
        assert entry.type in errors[0]
