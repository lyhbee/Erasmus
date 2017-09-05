import pytest
from urllib.parse import urlencode
from . import ServiceTest

from erasmus.services import BiblesOrg
from erasmus.data import Passage


class MockConfig:
    api_key = 'foo bar baz'


class TestBiblesOrg(ServiceTest):
    @pytest.fixture
    def service(self):
        config = MockConfig()
        return BiblesOrg(config)

    @pytest.fixture
    def good_mock_search(self, mocker, mock_response):
        return_value = {
            'response': {
                'search': {
                    'result': {
                        'summary': {
                            'total': 50
                        },
                        'verses': [
                            {'reference': 'John 1:1-4'},
                            {'reference': 'Genesis 50:1'}
                        ]
                    }
                }
            }
        }
        mocker.patch.object(mock_response, 'json',
                            new_callable=mocker.AsyncMock,
                            return_value=return_value)

        return mock_response

    @pytest.fixture
    def bad_mock_search(self, mocker, good_mock_search):
        good_mock_search.json.return_value = {
            'response': {
                'search': {
                }
            }
        }

        return good_mock_search

    @pytest.fixture
    def search_url(self):
        return 'https://bibles.org/v2/verses.js?' + urlencode({
            'keyword': 'one two three',
            'precision': 'all',
            'version': 'esv',
            'sort_order': 'canonical',
            'limit': 20
        })

    @pytest.fixture
    def good_mock_passages(self, mocker, mock_response):
        return_value = {
            'response': {
                'search': {
                    'result': {
                        'passages': [
                            {'text': '<p class=\"p\"><sup id=\"Gal.3.10\" class=\"v\">10</sup>'
                                     'For as many as are of the works of the Law are under a '
                                     'curse; for it is written, “C<span class=\"sc\">URSED IS '
                                     'EVERYONE WHO DOES NOT ABIDE BY ALL THINGS WRITTEN IN THE '
                                     'BOOK OF THE LAW</span>, <span class=\"sc\">TO '
                                     'PERFORM THEM</span>.”<sup id=\"Gal.3.11\" class=\"v\">11'
                                     '</sup>Now that no one is justified by the Law before God '
                                     'is evident; for, “T<span class=\"sc\">HE RIGHTEOUS MAN '
                                     'SHALL LIVE BY FAITH</span>.”</p>'}
                        ]
                    }
                }
            }
        }
        mocker.patch.object(mock_response, 'json',
                            new_callable=mocker.AsyncMock,
                            return_value=return_value)

        return mock_response

    @pytest.fixture
    def bad_mock_passages(self, mocker, good_mock_passages):
        good_mock_passages.json.return_value = {
            'response': {
                'search': {
                    'result': {
                        'passages': []
                    }
                }
            }
        }

        return good_mock_passages

    def get_passages_url(self, version: str, passage: Passage) -> str:
        return f'https://bibles.org/v2/passages.js?' + urlencode({
            'q[]': str(passage),
            'version': version
        })

    def test_init(self, service):
        super().test_init(service)

        assert service._auth.login == 'foo bar baz'
        assert service._auth.password == 'X'
