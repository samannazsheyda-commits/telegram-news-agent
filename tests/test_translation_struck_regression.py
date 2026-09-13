from src.services import translation_is_publishable


def test_struck_vessel_translation_accepts_esabat_wording():
    source = (
        "An Iranian commercial vessel was struck off Qeshm Island, "
        "leaving one killed and three wounded."
    )
    translated = (
        "یک شناور تجاری ایرانی در نزدیکی جزیره قشم مورد اصابت قرار گرفت؛ "
        "یک نفر کشته و سه نفر زخمی شدند."
    )

    assert translation_is_publishable(source, translated) is True
