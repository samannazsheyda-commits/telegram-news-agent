from src import services


def test_google_mobile_fallback_can_return_persian():
    class Resp:
        text = '<div class="result-container">ایران یک موشک شلیک کرد</div>'
        def raise_for_status(self):
            return None
    class Session:
        def get(self, *args, **kwargs):
            return Resp()
    assert services._google_mobile_translate('Iran launched a missile', session=Session()) == 'ایران یک موشک شلیک کرد'
