import pytest
from erasmus.data import Passage, SearchResults
from erasmus.exceptions import DoNotUnderstandError


@pytest.mark.usefixtures('mock_aiohttp')
class ServiceTest(object):
    @pytest.fixture
    def service(self):
        raise NotImplementedError

    @pytest.fixture
    def good_mock_search(self):
        raise NotImplementedError

    @pytest.fixture
    def bad_mock_search(self):
        raise NotImplementedError

    @pytest.fixture
    def search_url(self):
        raise NotImplementedError

    @pytest.fixture
    def good_mock_passages(self):
        raise NotImplementedError

    @pytest.fixture
    def bad_mock_passages(self):
        raise NotImplementedError

    def get_passages_url(self, version: str, passage: Passage) -> str:
        raise NotImplementedError

    def test_init(self, service):
        assert service is not None

    @pytest.mark.asyncio
    @pytest.mark.usefixtures('good_mock_search')
    async def test_search(self, mocker, mock_client_session, service, search_url):
        response = await service.search('esv', ['one', 'two', 'three'])

        assert mock_client_session.get.call_args == mocker.call(search_url)
        assert response == SearchResults([
            Passage.from_string('John 1:1-4'),
            Passage.from_string('Genesis 50:1')
        ], 50)

    @pytest.mark.asyncio
    @pytest.mark.usefixtures('bad_mock_search')
    async def test_search_bad_response(self, mocker, mock_client_session, service):
        with pytest.raises(DoNotUnderstandError):
            await service.search('esv', ['one', 'two', 'three'])

    @pytest.mark.parametrize('args', [
        ['esv', Passage.from_string('John 1:2-3')],
        ['nasb', Passage.from_string('Mark 5:20')]
    ])
    @pytest.mark.asyncio
    @pytest.mark.usefixtures('good_mock_passages')
    async def test_get_passage(self, args, mocker, mock_client_session,
                               service):
        response = await service.get_passage(*args)
        passages_url = self.get_passages_url(*args)
        assert mock_client_session.get.call_args == mocker.call(passages_url)
        assert response == ('10. For as many as are of the works of the Law are under a '
                            'curse; for it is written, “CURSED IS EVERYONE WHO DOES NOT '
                            'ABIDE BY ALL THINGS WRITTEN IN THE BOOK OF THE LAW, TO '
                            'PERFORM THEM.” 11. Now that no one is justified by the Law '
                            'before God is evident; for, “THE RIGHTEOUS MAN SHALL LIVE BY '
                            'FAITH.”')

    @pytest.mark.asyncio
    @pytest.mark.usefixtures('bad_mock_passages')
    async def test_get_passage_no_passages(self, service):
        with pytest.raises(DoNotUnderstandError):
            await service.get_passage('esv', Passage.from_string('John 1:2-3'))
