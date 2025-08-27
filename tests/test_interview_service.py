import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.interview_service import InterviewService
from app.core.config import Settings


@pytest.fixture
def mock_settings():
    settings = Mock(spec=Settings)
    settings.openai_api_key = "test-key"
    settings.openai_base_url = None
    settings.openai_timeout_seconds = 60
    settings.openai_max_retries = 3
    settings.openai_model = "gpt-4o-mini"
    return settings


@pytest.fixture
def mock_salesforce_client():
    client = Mock()
    client.query_opportunity_discussed_by_id.return_value = {
        "TR1__Candidate__r": {
            "Candidate_s_Resume_TXT__c": "Experienced software developer with 5 years in Python and JavaScript"
        }
    }
    return client


@pytest.fixture
def interview_service(mock_settings, mock_salesforce_client):
    with patch('app.services.interview_service.SalesforceClient') as mock_sf_class:
        mock_sf_class.return_value = mock_salesforce_client
        service = InterviewService(settings=mock_settings)
        return service


class TestInterviewService:
    
    @pytest.mark.asyncio
    async def test_start_interview_success(self, interview_service):
        """Test successful interview start"""
        with patch.object(interview_service, '_client') as mock_client:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = """
            POSITION: Senior Python Developer
            QUESTION 1: Do you have 5+ years of Python experience?
            QUESTION 2: Have you worked with modern web frameworks?
            QUESTION 3: Do you have experience with JavaScript?
            """
            mock_client.chat.completions.create.return_value = mock_response
            
            result = await interview_service.start_interview("test123")
            
            assert "interview_id" in result
            assert result["record_id"] == "test123"
            assert result["position_title"] == "Senior Python Developer"
            assert len(result["yes_no_questions"]) == 3
            assert "Do you have 5+ years of Python experience?" in result["yes_no_questions"]
    
    @pytest.mark.asyncio
    async def test_start_interview_no_resume(self, interview_service, mock_salesforce_client):
        """Test interview start with no resume text"""
        mock_salesforce_client.query_opportunity_discussed_by_id.return_value = {
            "TR1__Candidate__r": {}
        }
        
        with pytest.raises(ValueError, match="Candidate resume text not found"):
            await interview_service.start_interview("test123")
    
    @pytest.mark.asyncio
    async def test_submit_yes_no_answers_success(self, interview_service):
        """Test successful yes/no answers submission"""
        # First start an interview
        with patch.object(interview_service, '_client') as mock_client:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = """
            POSITION: Senior Python Developer
            QUESTION 1: Do you have 5+ years of Python experience?
            QUESTION 2: Have you worked with modern web frameworks?
            QUESTION 3: Do you have experience with JavaScript?
            """
            mock_client.chat.completions.create.return_value = mock_response
            
            await interview_service.start_interview("test123")
            interview_id = list(interview_service._interview_sessions.keys())[0]
            
            # Mock open-ended questions generation
            mock_response.choices[0].message.content = """
            QUESTION 1: Can you describe a challenging project you've worked on?
            QUESTION 2: What motivates you in your work?
            """
            
            result = await interview_service.submit_yes_no_answers(interview_id, [True, False, True])
            
            assert result["interview_id"] == interview_id
            assert result["yes_no_answers"]["answers"] == [True, False, True]
            assert len(result["open_ended_questions"]) == 2
    
    @pytest.mark.asyncio
    async def test_complete_interview_success(self, interview_service):
        """Test successful interview completion"""
        # Start interview and submit yes/no answers
        with patch.object(interview_service, '_client') as mock_client:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = """
            POSITION: Senior Python Developer
            QUESTION 1: Do you have 5+ years of Python experience?
            QUESTION 2: Have you worked with modern web frameworks?
            QUESTION 3: Do you have experience with JavaScript?
            """
            mock_client.chat.completions.create.return_value = mock_response
            
            await interview_service.start_interview("test123")
            interview_id = list(interview_service._interview_sessions.keys())[0]
            
            # Mock open-ended questions
            mock_response.choices[0].message.content = """
            QUESTION 1: Can you describe a challenging project you've worked on?
            QUESTION 2: What motivates you in your work?
            """
            
            await interview_service.submit_yes_no_answers(interview_id, [True, False, True])
            
            # Mock summary generation
            mock_response.choices[0].message.content = "This is a comprehensive interview summary."
            
            # Mock Salesforce save
            with patch.object(interview_service, '_save_interview_to_salesforce') as mock_save:
                result = await interview_service.complete_interview(interview_id, [
                    "I worked on a complex e-commerce platform",
                    "I'm motivated by solving challenging problems"
                ])
                
                assert result["interview_id"] == interview_id
                assert "summary" in result
                assert result["message"] == "Interview completed and saved to Salesforce."
                mock_save.assert_called_once()
    
    def test_get_interview_session(self, interview_service):
        """Test getting interview session"""
        # Create a mock session
        interview_service._interview_sessions["test123"] = {"test": "data"}
        
        session = interview_service.get_interview_session("test123")
        assert session == {"test": "data"}
        
        # Test non-existent session
        session = interview_service.get_interview_session("nonexistent")
        assert session is None
    
    def test_cleanup_interview_session(self, interview_service):
        """Test cleaning up interview session"""
        # Create a mock session
        interview_service._interview_sessions["test123"] = {"test": "data"}
        
        # Verify session exists
        assert "test123" in interview_service._interview_sessions
        
        # Clean up
        interview_service.cleanup_interview_session("test123")
        
        # Verify session is removed
        assert "test123" not in interview_service._interview_sessions
