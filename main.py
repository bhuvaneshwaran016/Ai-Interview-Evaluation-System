from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, inspect, text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship
from pydantic import BaseModel
import sys

# ALWAYS force UTF-8 encoding so emojis (✅, ❌, etc.) don't crash Windows terminals!
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

print("[1/20] Imports starting...")
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    print("⚠️ pdfplumber not available - PDF processing will be limited")
print("[2/20] Import pdfplumber...")
import io
import re
import requests
print("[3/20] Import requests...")
import json
import bcrypt
import cloudinary
import cloudinary.uploader
import os
import tempfile
import numpy as np
from dotenv import load_dotenv

# ========== IMPORT FASTER-WHISPER AT MODULE LEVEL ==========
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
    print("[4/20] Faster-Whisper imported successfully")
except ImportError as e:
    FASTER_WHISPER_AVAILABLE = False
    WhisperModel = None
    print(f"⚠️ Faster-Whisper not available: {e}")
    print("    Install with: pip install faster-whisper==1.0.3")

print("[5/20] Base imports done...")

# Create videos directory for local storage
VIDEOS_DIR = os.path.join(os.getcwd(), "videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

# Load environment variables from .env file
load_dotenv()

# ========== CLOUDINARY CONFIG ==========
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# ========== DATABASE CONFIG ==========
DATABASE_URL = os.getenv("DATABASE_URL")

# Defer engine creation with connect_args to avoid Windows hangs
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 10},
    echo=False
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ========== PASSWORD HASHING (direct bcrypt, no passlib) ==========
def hash_password(password: str) -> str:
    """Hash password using bcrypt directly — no passlib dependency issues"""
    pwd_bytes = password.encode('utf-8')[:72]  # bcrypt max 72 bytes
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against stored hash using bcrypt directly"""
    try:
        pwd_bytes = plain.encode('utf-8')[:72]  # bcrypt max 72 bytes
        return bcrypt.checkpw(pwd_bytes, hashed.encode('utf-8'))
    except Exception:
        return False


whisper_model = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        if not FASTER_WHISPER_AVAILABLE or WhisperModel is None:
            raise ImportError("Faster-Whisper is not installed. Install with: pip install faster-whisper==1.0.3")
        try:
            print("⏳ Loading Faster-Whisper AI model lazily...")
            # Use "auto" to detect device (GPU if available, else CPU), int8 for faster processing
            whisper_model = WhisperModel("medium", device="auto", compute_type="int8")
            print("✅ Faster-Whisper model loaded")
        except Exception as e:
            print(f"❌ Failed to load Faster-Whisper model: {e}")
            raise
    return whisper_model


import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

# Auto-cleanup time (in minutes)
# Any interview data older than this will be deleted automatically from DB and Cloudinary
# Set to 7 minutes for auto-cleanup of questions, transcriptions, expressions, and answers
VIDEO_EXPIRY_MINUTES = 10
async def auto_delete_old_videos():
    """Auto-delete interview data (questions, transcriptions, expressions, answers) after 7 minutes.
    Uses email as identifier to delete all related data for a candidate."""
    while True:
        try:
            db = SessionLocal()
            cutoff_time = datetime.utcnow() - timedelta(minutes=VIDEO_EXPIRY_MINUTES)
            cutoff_str = cutoff_time.isoformat()
            
            # Find old videos where created_at is older than cutoff (7 minutes)
            old_videos = db.query(InterviewVideo).filter(InterviewVideo.created_at < cutoff_str).all()
            
            if old_videos:
                print(f"\n🗑️ Found {len(old_videos)} expired interview videos (>7 mins)")
            
            for video in old_videos:
                try:
                    # Get candidate info via email for logging
                    candidate = db.query(Candidate).filter(Candidate.id == video.candidate_id).first()
                    candidate_email = candidate.email if candidate else "unknown"
                    
                    print(f"\n🗑️ Auto-deleting expired interview data:")
                    print(f"   📧 Candidate Email: {candidate_email}")
                    print(f"   🎥 Video ID: {video.id}")
                    print(f"   ❓ Question: {video.question_text[:50] if video.question_text else 'N/A'}...")
                    
                    # 1. Delete question_text
                    if video.question_text:
                        print(f"   ✓ Removing question text")
                        video.question_text = None
                    
                    # 2. Delete transcription (extracted voice-to-text answer)
                    if video.transcription:
                        print(f"   ✓ Removing transcription/answer text")
                        video.transcription = None
                    
                    # 3. Delete expression analysis
                    if video.expression_analysis:
                        print(f"   ✓ Removing expression analysis")
                        video.expression_analysis = None
                    
                    # 4. Delete AI feedback
                    if video.ai_feedback:
                        print(f"   ✓ Removing AI feedback")
                        video.ai_feedback = None
                    
                    # 5. Delete from Cloudinary using public_id
                    if video.public_id:
                        try:
                            print(f"   ✓ Removing video from Cloudinary")
                            cloudinary.uploader.destroy(video.public_id, resource_type="video")
                        except Exception as ce:
                            print(f"   ⚠️ Cloudinary deletion warning: {ce}")
                    
                    # 6. Delete entire video record from Database
                    print(f"   ✓ Removing record from database")
                    db.delete(video)
                    db.commit()
                    
                    print(f"✅ Expired interview data deleted successfully for {candidate_email}")
                    
                except Exception as e:
                    print(f"❌ Error auto-deleting video {video.id}: {e}")
                    db.rollback()
            
            db.close()
        except Exception as e:
            print(f"❌ Cleanup loop error: {e}")
        
        # Check again every 1 minute for faster cleanup detection
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure schema exists before startup work begins
    try:
        initialize_database()
    except Exception as e:
        print(f"⚠️ Database initialization failed: {e}")

    # Start the background polling task silently
    cleanup_task = asyncio.create_task(auto_delete_old_videos())
    # Disable startup reprocessing to allow fast server startup
    # Users can manually run: python simple_transcribe_workflow.py
    # startup_reprocess_task = asyncio.create_task(reprocess_unprocessed_videos_on_startup())
    yield
    # Clean up the tasks on shutdown
    cleanup_task.cancel()
    # startup_reprocess_task.cancel()


def delete_candidate_interview_data_by_email(candidate_email: str, db: Session = None):
    """Manual cleanup: Delete ALL interview data for a candidate by email.
    Clears: questions, transcriptions (answers), expressions, feedback, and videos from cloud.
    
    Can be called from CLI or API endpoint.
    
    Example:
        delete_candidate_interview_data_by_email("user@example.com")
    """
    if db is None:
        db = SessionLocal()
    
    try:
        # 1. Find candidate by email
        candidate = db.query(Candidate).filter(Candidate.email == candidate_email).first()
        if not candidate:
            print(f"❌ Candidate not found: {candidate_email}")
            return False
        
        # 2. Find all videos for this candidate
        videos = db.query(InterviewVideo).filter(InterviewVideo.candidate_id == candidate.id).all()
        
        if not videos:
            print(f"ℹ️ No interview data found for {candidate_email}")
            return True
        
        print(f"\n🗑️ DELETING ALL INTERVIEW DATA FOR: {candidate_email}")
        print(f"   📊 Found {len(videos)} interview videos to process")
        
        # 3. Delete each video and its data one by one
        deleted_count = 0
        for i, video in enumerate(videos, 1):
            try:
                print(f"\n   [{i}/{len(videos)}] Processing Video ID {video.id}:")
                
                # Show what's being deleted
                if video.question_text:
                    q_preview = video.question_text[:40] + "..." if len(video.question_text) > 40 else video.question_text
                    print(f"       ✓ Question: {q_preview}")
                
                if video.transcription:
                    a_preview = video.transcription[:40] + "..." if len(video.transcription) > 40 else video.transcription
                    print(f"       ✓ Answer (transcription): {a_preview}")
                
                if video.expression_analysis:
                    print(f"       ✓ Expression analysis data")
                
                if video.ai_feedback:
                    print(f"       ✓ AI feedback")
                
                # Delete video from Cloudinary
                if video.public_id:
                    try:
                        print(f"       ✓ Cloudinary video (ID: {video.public_id})")
                        cloudinary.uploader.destroy(video.public_id, resource_type="video")
                    except Exception as ce:
                        print(f"       ⚠️ Cloudinary issue (non-critical): {str(ce)[:50]}")
                
                # Delete from database
                db.delete(video)
                deleted_count += 1
                
            except Exception as e:
                print(f"       ❌ Error processing video: {e}")
        
        db.commit()
        print(f"\n✅ SUCCESS: Deleted {deleted_count} interview records for {candidate_email}")
        print(f"   • Questions: Cleared")
        print(f"   • Transcriptions/Answers: Cleared")
        print(f"   • Expressions: Cleared")
        print(f"   • AI Feedback: Cleared")
        print(f"   • Cloudinary Videos: Deleted")
        print(f"   • Database Records: Deleted")
        return True
        
    except Exception as e:
        print(f"❌ Error in cleanup: {e}")
        db.rollback()
        return False
    finally:
        db.close()


async def reprocess_unprocessed_videos_on_startup():
    """Queue missing videos for transcription when the app starts."""
    await asyncio.sleep(5)
    db = SessionLocal()
    try:
        videos = db.query(InterviewVideo).filter(
            (InterviewVideo.transcription == None)
        ).order_by(InterviewVideo.created_at.desc()).limit(5).all()
        if videos:
            print(f"⚠️ Found {len(videos)} unprocessed video(s); reprocessing now...")
            for video in videos:
                asyncio.create_task(asyncio.to_thread(transcribe_video_only_task, video.id))
                await asyncio.sleep(0.2)
    except Exception as e:
        print(f"⚠️ Startup reprocessing failed: {e}")
    finally:
        db.close()

# ========== FASTAPI APP ==========
app = FastAPI(lifespan=lifespan)

# Enable CORS for frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== DATABASE MODEL ==========
class Candidate(Base):
    __tablename__ = "candidates"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String)
    experience = Column(Integer)
    year = Column(Integer)
    created_at = Column(String)  # ensure compatibility with existing schema

    details = relationship('Details', back_populates='candidate', cascade='all, delete-orphan')

class Details(Base):
    __tablename__ = "details"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=False)
    skills = Column(String)
    project_title = Column(String)
    github_link = Column(String)
    resume_url = Column(String)
    created_at = Column(String)

    candidate = relationship('Candidate', back_populates='details')

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(String)

class InterviewVideo(Base):
    __tablename__ = "interview_video"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey('candidates.id'), nullable=False)
    session_id = Column(String, nullable=False)         # Unique session identifier for each interview
    question_index = Column(Integer, nullable=False)   # 0-based question number
    question_text = Column(String)
    video_url = Column(String, nullable=False)          # Cloudinary secure URL
    public_id = Column(String)                          # Cloudinary public_id (for deletion later)
    transcription = Column(String)                      # Extracted text from audio
    expression_analysis = Column(String)                # MediaPipe Face Landmarker expressions
    ai_feedback = Column(String)                        # Ollama Score and Evaluation
    created_at = Column(String)

    candidate = relationship('Candidate', backref='videos')

class UserRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str
    experience: int
    phone: str

class CompanyRequest(BaseModel):
    company_name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ========== DATABASE SETUP (SAFE) ==========
def initialize_database():
    """Initialize database schema safely when the app starts."""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if 'interview_video' in inspector.get_table_names():
        iv_cols = inspector.get_columns('interview_video')
        iv_col_names = {col['name'] for col in iv_cols}
        with engine.connect() as conn:
            if 'session_id' not in iv_col_names:
                print('⚠️ Adding session_id column to interview_video table')
                try:
                    conn.execute(text("ALTER TABLE interview_video ADD COLUMN session_id VARCHAR NOT NULL DEFAULT 'legacy'"))
                    print('✅ session_id column added successfully')
                except Exception as e:
                    print(f'⚠️ Could not add session_id column: {e}. Session management will be limited.')
            if 'transcription' not in iv_col_names:
                print('⚠️ Adding transcription column to interview_video table')
                conn.execute(text('ALTER TABLE interview_video ADD COLUMN transcription VARCHAR'))
            if 'expression_analysis' not in iv_col_names:
                print('⚠️ Adding expression_analysis column to interview_video table')
                conn.execute(text('ALTER TABLE interview_video ADD COLUMN expression_analysis VARCHAR'))
            if 'ai_feedback' not in iv_col_names:
                print('⚠️ Adding ai_feedback column to interview_video table')
                conn.execute(text('ALTER TABLE interview_video ADD COLUMN ai_feedback VARCHAR'))
            conn.commit()

# ========== DATABASE SESSION ==========
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ========== PDF PARSING HELPERS ==========

def extract_github_link(text: str) -> str:
    match = re.search(r'https?://(?:www\.)?github\.com/[A-Za-z0-9_.\-\/]+', text, flags=re.I)
    return match.group(0).strip() if match else ""


def extract_skills(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        lower = line.lower()
        if 'skill' in lower:
            if ':' in line:
                return line.split(':', 1)[1].strip()
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return ""


def extract_project_title(text: str) -> str:
    match = re.search(r'(?:project title|projects|project)\s*[:\-–]?\s*(.+)', text, flags=re.I)
    if match:
        value = match.group(1).strip()
        if value:
            return value

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        lower = line.lower()
        if lower in ('project', 'projects', 'project title') and i + 1 < len(lines):
            return lines[i + 1].strip()
    return ""


# ========== API ENDPOINTS ==========

@app.get("/")
def read_root():
    """Health check endpoint"""
    return {"message": "✓ API is running!", "status": "online"}

@app.post("/add_user")
def add_user(user: UserRequest, db: Session = Depends(get_db)):
    """User signup endpoint"""
    try:
        existing = db.query(Candidate).filter(Candidate.email == user.email).first()
        if existing:
            return {"error": "Email already exists"}

        hashed_password = hash_password(user.password)
        print(f"✅ Password hashed successfully")

        new_user = Candidate(
            full_name=user.name,
            email=user.email,
            phone=user.phone,
            password=hashed_password,
            role=user.role,
            experience=user.experience
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        print(f"✅ User created: {new_user.email}")
        return {"message": "User registered successfully", "user_id": new_user.id}
    
    except Exception as e:
        print(f"❌ Signup error: {str(e)}")
        db.rollback()
        return {"error": f"Database error: {str(e)}"}

@app.post("/student/login")
def login(user: LoginRequest, db: Session = Depends(get_db)):
    """User login endpoint"""
    try:
        db_user = db.query(Candidate).filter(Candidate.email == user.email).first()

        if not db_user:
            return {"error": "User not found"}

        if not verify_password(user.password, db_user.password):
            return {"error": "Wrong password"}

        return {
            "message": "Login successful",
            "user_id": db_user.id,
            "name": db_user.full_name,
            "role": db_user.role
        }
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        return {"error": f"Login error: {str(e)}"}

@app.post("/company/register")
def company_register(company: CompanyRequest, db: Session = Depends(get_db)):
    """Company registration endpoint"""
    try:
        existing = db.query(Company).filter(Company.email == company.email).first()
        if existing:
            return {"error": "Email already exists"}

        hashed_password = hash_password(company.password)

        new_company = Company(
            company_name=company.company_name,
            email=company.email,
            password=hashed_password
        )

        db.add(new_company)
        db.commit()
        db.refresh(new_company)

        return {"message": "Company registered successfully", "company_id": new_company.id}
    except Exception as e:
        print(f"❌ Company registration error: {str(e)}")
        db.rollback()
        return {"error": f"Database error: {str(e)}"}

@app.post("/company/login")
def company_login(company: LoginRequest, db: Session = Depends(get_db)):
    """Company login endpoint"""
    try:
        db_company = db.query(Company).filter(Company.email == company.email).first()
        if not db_company:
            return {"error": "Company not found"}

        if not verify_password(company.password, db_company.password):
            return {"error": "Wrong password"}

        return {
            "message": "Login successful",
            "company_id": db_company.id,
            "company_name": db_company.company_name,
            "email": db_company.email
        }
    except Exception as e:
        print(f"❌ Company login error: {str(e)}")
        return {"error": f"Login error: {str(e)}"}

@app.post("/upload-resume")
async def upload_resume(
    email: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a PDF resume, parse skills/project/github, and save them to the candidate record."""
    try:
        if not file.filename.lower().endswith('.pdf'):
            return {"error": "Only PDF files are allowed"}

        candidate = db.query(Candidate).filter(Candidate.email == email).first()
        if not candidate:
            return {"error": "Candidate not found for provided email"}

        content = await file.read()
        if not PDFPLUMBER_AVAILABLE:
            return {"error": "PDF processing not available - pdfplumber not installed"}
        
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        details = Details(
            candidate_id=candidate.id,
            skills=extract_skills(text),
            project_title=extract_project_title(text),
            github_link=extract_github_link(text),
            resume_url=file.filename,
            created_at=""
        )

        db.add(details)
        db.commit()
        db.refresh(details)

        return {
            "message": "Resume parsed and saved to details table successfully",
            "candidate_email": candidate.email,
            "details_id": details.id,
            "skills": details.skills,
            "project_title": details.project_title,
            "github_link": details.github_link,
            "resume_url": details.resume_url,
        }
    except Exception as e:
        db.rollback()
        return {"error": f"Error processing resume: {str(e)}"}


@app.get("/details")
def get_details(email: str, db: Session = Depends(get_db)):
    """Fetch parsed details rows for a candidate email."""
    candidate = db.query(Candidate).filter(Candidate.email == email).first()
    if not candidate:
        return {"error": "Candidate not found"}

    rows = db.query(Details).filter(Details.candidate_id == candidate.id).all()
    return {
        "candidate_email": candidate.email,
        "count": len(rows),
        "details": [
            {
                "id": item.id,
                "skills": item.skills,
                "project_title": item.project_title,
                "github_link": item.github_link,
                "resume_url": item.resume_url,
                "created_at": item.created_at,
            }
            for item in rows
        ],
    }


@app.post("/generate-questions")
async def generate_questions(email: str = Form(...), db: Session = Depends(get_db)):
    """Generate interview questions using Ollama based on candidate's skills and project title"""
    try:
        # Get candidate details
        candidate = db.query(Candidate).filter(Candidate.email == email).first()
        if not candidate:
            print(f"❌ Candidate not found: {email}")
            return {
                "error": "Candidate not found",
                "questions": [
                    "Can you describe a technical challenge you solved recently?",
                    "What is your experience with your primary programming language?",
                    "How do you approach learning new technologies?",
                    "Tell me about your most significant project to date.",
                    "How do you handle debugging and troubleshooting in your work?"
                ]
            }

        # Get the latest details record for this candidate
        details = db.query(Details).filter(Details.candidate_id == candidate.id).order_by(Details.id.desc()).first()
        
        # If no details, use fallback questions
        if not details:
            print(f"⚠️  No resume details found for {email}, using fallback questions")
            fallback = [
                "Can you describe a technical challenge you solved recently?",
                "What is your experience with your primary programming language?",
                "How do you approach learning new technologies?",
                "Tell me about your most significant project to date.",
                "How do you handle debugging and troubleshooting in your work?"
            ]
            return {
                "message": "Using fallback questions (no resume details)",
                "candidate_email": candidate.email,
                "questions": fallback
            }

        # Prepare the prompt for Ollama
        skills = details.skills or "Not specified"
        project_title = details.project_title or "Not specified"
        
        prompt = f"""You are a technical interviewer. Based on the candidate's skills and project, generate exactly 5 interview questions.
Skills: {skills}
Project: {project_title}

Return ONLY a numbered list of 5 questions. Do not include any intro, outro, or conversation.
Example:
1. What is your experience with...?
2. How did you handle...?
"""

        # Call Ollama API
        try:
            print(f"🤖 Requesting questions from Ollama (model: llama3) for {email}...")
            response = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7
                    }
                },
                timeout=45
            )
            
            if response.status_code != 200:
                print(f"❌ Ollama API returned status {response.status_code}")
                return {"error": f"Ollama API error: {response.status_code}"}
            
            response_data = response.json()
            questions_text = response_data.get("response", "").strip()
            print(f"🤖 Ollama raw response received (length: {len(questions_text)})")
            
            # Parse questions reliably
            # 1. Standardize line endings and split
            # Ensure numbers start on a new line to handle models returning questions on a single line
            questions_text = re.sub(r'(\b\d+[\.\)\-])', r'\n\1', questions_text)
            
            # Force bullet points and question marks to create line breaks to guarantee separation!
            questions_text = questions_text.replace('?', '?\n')
            questions_text = questions_text.replace('*', '\n*')
            questions_text = questions_text.replace('•', '\n•')
            
            lines = questions_text.split('\n')
            
            questions = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if the line starts with a number (likely a real question)
                is_numbered = re.match(r'^\s*\d+[\.\)\-]', line)
                
                # Remove leading numbers and symbols
                clean_line = re.sub(r'^\s*(\d+[\.\)\-]?|Q\d+[:\.]?|[\-\*•])\s*', '', line).strip()
                clean_line = clean_line.replace('*', '').replace('_', '')
                
                # Exclude obvious intro/outro fillers
                lower_line = clean_line.lower()
                fillers = ["here are", "sure", "based on", "interview questions", "technical questions", "the 5", "this list", "skills:", "project:"]
                
                is_filler = any(f in lower_line for f in fillers)
                
                # If it's a numbered list item OR it has a question mark and isn't filler, it's a candidate
                if (is_numbered or '?' in clean_line) and not is_filler and len(clean_line) > 8:
                    questions.append(clean_line)

            print(f"✅ Extracted {len(questions)} technical questions from Ollama")

            # Fallback/Padding logic to ensure exactly 5 technical questions
            pool = [
                f"Can you explain your experience working with {skills} in a real-world scenario?",
                f"What was the most significant technical challenge you faced while developing '{project_title}'?",
                "How do you ensure your code is maintainable and scalable when working on large projects?",
                "Can you describe your process for debugging complex logic errors in your applications?",
                "How do you keep up with the latest trends and best practices in your technical field?",
                "What tools or libraries do you find most essential for your development workflow?",
                "Can you walk me through a time you had to optimize a piece of code for better performance?",
                "How do you handle technical debt and code refactoring in your projects?"
            ]

            # 1. If we got zero or very few questions, use the pool
            if len(questions) < 2:
                questions = pool[:5]
            
            # 2. If we got some but less than 5, pad with unique questions from the pool
            elif len(questions) < 5:
                already_in_lower = [q.lower() for q in questions]
                for p_q in pool:
                    if len(questions) >= 5:
                        break
                    # Avoid adding duplicates
                    if p_q.lower() not in already_in_lower:
                         questions.append(p_q)
                
                # Ultimate fallback padding
                while len(questions) < 5:
                    questions.append("Can you explain a technical concept you recently learned and implemented?")

            # 3. Ensure strictly 5 questions and clean them up (CRITICAL: slice to exactly 5)
            questions = [q.strip() for q in questions[:5]]
            
            # Final verification - ALWAYS return exactly 5 questions
            if len(questions) != 5:
                print(f"⚠️ WARNING: Got {len(questions)} questions, forcing exactly 5")
                while len(questions) < 5:
                    questions.append("Can you describe a technical challenge you solved recently?")
                questions = questions[:5]
            
            print(f"✅ RETURNING EXACTLY 5 QUESTIONS: {len(questions)} questions")
                
            return {
                "message": "Interview questions generated successfully",
                "candidate_email": candidate.email,
                "skills": skills,
                "project_title": project_title,
                "questions": questions
            }
        except requests.exceptions.ConnectionError:
            print("❌ Connection Error: Ollama is not running.")
            return {"error": "Cannot connect to Ollama. Make sure Ollama is running on localhost:11434"}
        except requests.exceptions.Timeout:
            print("❌ Timeout Error: Ollama took too long.")
            return {"error": "Ollama request timed out"}

    except Exception as e:
        return {"error": f"Error generating questions: {str(e)}"}


def upload_cloudinary_bg(record_id: int, video_path: str, public_id: str):
    db: Session = SessionLocal()
    try:
        try:
            print(f"☁️ Starting background Cloudinary upload for {video_path}...")
            upload_result = cloudinary.uploader.upload(
                video_path,
                resource_type="video",
                folder="interview_videos",
                public_id=public_id,
                overwrite=True,
                use_filename=True,
                unique_filename=False,
                timeout=120
            )
            cloud_url = upload_result.get('secure_url') or upload_result.get('url')
            cloud_public_id = upload_result.get('public_id')
            
            # Update DB with real cloud URL
            record = db.query(InterviewVideo).filter(InterviewVideo.id == record_id).first()
            if record:
                record.video_url = cloud_url
                record.public_id = cloud_public_id
                db.commit()
                print(f"✅ Background Cloudinary upload success: {cloud_url}")
        except Exception as e:
            print(f"❌ Background Cloudinary upload failed: {e}")
    finally:
        db.close()


@app.post("/upload-video")
async def upload_video(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    session_id: str = Form(default="default_session"),
    question_index: int = Form(...),
    question_text: str = Form(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Save video locally and process for transcription and expressions."""
    try:
        print(f"📤 Starting upload for {email}, question {question_index}")

        # ── HARD LIMIT: Only allow exactly 5 questions (index 0–4) ──
        if question_index < 0 or question_index > 4:
            print(f"❌ Rejected upload: question_index {question_index} is outside 0–4 range")
            return {"error": f"Invalid question index {question_index}. Only 5 questions (0–4) are allowed."}

        # Validate candidate exists
        candidate = db.query(Candidate).filter(Candidate.email == email).first()
        if not candidate:
            print(f"❌ Candidate not found: {email}")
            return {"error": "Candidate not found"}

        # ── DEDUPLICATE: If same question already uploaded for this session, delete old one first ──
        # Doing this BEFORE the limit check allows users to re-record a specific question
        # even if they have already uploaded 5 videos in total.
        duplicate = db.query(InterviewVideo).filter(
            InterviewVideo.candidate_id == candidate.id,
            InterviewVideo.session_id == session_id,
            InterviewVideo.question_index == question_index
        ).first()
        if duplicate:
            print(f"♻️ Replacing existing answer for Q{question_index + 1} in session {session_id}")
            db.delete(duplicate)
            db.commit()
            print(f"✅ Old Q{question_index + 1} answer removed from Database, uploading new one...")

        # ── HARD LIMIT: Reject if this candidate already has 5 uploaded videos for this session ──
        existing_count = db.query(InterviewVideo).filter(
            InterviewVideo.candidate_id == candidate.id,
            InterviewVideo.session_id == session_id
        ).count()
        if existing_count >= 5:
            print(f"❌ Rejected upload: candidate {email} already has {existing_count} videos for session {session_id}")
            return {"error": "Maximum of 5 video answers already uploaded for this interview session."}

        # Get file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Seek back to beginning
        print(f"📏 File size: {file_size} bytes")

        # Save upload data to memory and local file
        content = await file.read()
        video_filename = f"{candidate.id}_{session_id}_q{question_index}_{int(__import__('time').time())}.webm"
        video_path = os.path.join(VIDEOS_DIR, video_filename)

        with open(video_path, "wb") as f:
            f.write(content)

        print(f"✅ Video saved locally: {video_path}")

        # Save to database INITIAL local fallback to make frontend snappy!
        public_id = f"{candidate.id}_{session_id}_q{question_index}_{int(__import__('time').time())}"
        from datetime import datetime
        record = InterviewVideo(
            candidate_id=candidate.id,
            question_index=question_index,
            question_text=question_text,
            video_url=video_path, 
            public_id=f"pending_{public_id}",
            created_at=datetime.utcnow().isoformat()
        )
        
        # Try to set session_id if the column exists
        try:
            record.session_id = session_id
        except AttributeError:
            # Column doesn't exist yet, skip for now
            print(f"⚠️ session_id column not available, using legacy mode")
        
        db.add(record)
        db.commit()
        db.refresh(record)

        print(f"✅ Video recorded in database locally: {video_path}")
        
        # ── DISPATCH BACKGROUND TASK ──
        background_tasks.add_task(upload_cloudinary_bg, record.id, video_path, public_id)
        
        return {
            "message": "Video successfully saved locally. Background upload started.",
            "video_id": record.id,
            "video_url": video_path,
            "question_index": question_index,
            "candidate_id": candidate.id,
            "public_id": f"pending_{public_id}",
        }

    except Exception as e:
        db.rollback()
        print(f"❌ Upload video error: {str(e)}")
        return {"error": f"Upload error: {str(e)}"}


@app.get("/interview-videos")
def get_interview_videos(email: str, db: Session = Depends(get_db)):
    """Fetch all recorded interview video URLs for a candidate."""
    candidate = db.query(Candidate).filter(Candidate.email == email).first()
    if not candidate:
        return {"error": "Candidate not found"}

    videos = db.query(InterviewVideo).filter(
        InterviewVideo.candidate_id == candidate.id
    ).order_by(InterviewVideo.question_index).all()

    return {
        "candidate_email": email,
        "total_videos": len(videos),
        "videos": [
            {
                "id": v.id,
                "question_index": v.question_index,
                "question_text": v.question_text,
                "video_url": v.video_url,
                "session_id": getattr(v, 'session_id', 'default_session'),
                "created_at": v.created_at,
            }
            for v in videos
        ],
    }


@app.post("/extract-pdf")
async def extract_pdf(file: UploadFile = File(...)):
    """Extract text from uploaded PDF"""
    try:
        if not file.filename.endswith('.pdf'):
            return {"error": "Only PDF files are allowed"}
        
        if not PDFPLUMBER_AVAILABLE:
            return {"error": "PDF processing not available - pdfplumber not installed"}
        
        # Read file content
        content = await file.read()
        
        # Extract text using pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = ""
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        
        return {"text": text.strip()}
    except Exception as e:
        return {"error": f"Error extracting text: {str(e)}"}

# ========== AI MODELS CACHE ==========
# Faster-Whisper will load lazily on first transcription request

# Windows Path Fix: Add the 't' directory to path to find DeepFace/TensorFlow
# (This bypasses the 260-character limit from the deep venv folder)
import sys
import os
import cv2

t_path = os.path.abspath('t')
if os.path.exists(t_path) and t_path not in sys.path:
    sys.path.insert(0, t_path)  # Insert at 0 so it overrides broken venv packages

# ========== IMPORT AUDIO & FACE DETECTION MODULES ==========
try:
    from audio_enhancement import process_audio_pipeline, validate_audio_content
    AUDIO_ENHANCEMENT_AVAILABLE = True
    print("✅ Audio enhancement module loaded")
except ImportError as e:
    print(f"⚠️ Audio enhancement not available: {e}")
    AUDIO_ENHANCEMENT_AVAILABLE = False

try:
    from face_detection import FaceDetectionPipeline, simple_face_detection, estimate_expressions_from_video
    FACE_DETECTION_AVAILABLE = True
    print("✅ Advanced face detection module loaded")
except ImportError as e:
    print(f"⚠️ Advanced face detection not available: {e}")
    FACE_DETECTION_AVAILABLE = False

# ========== WHISPER TRANSCRIPTION WITH IMPROVEMENTS ==========
def process_single_video_task(video_id: int):
    """Improved video processing: Enhanced audio transcription + Accurate face expression detection"""
    db = SessionLocal()
    try:
        import subprocess
        import imageio_ffmpeg
        import shutil
        import requests
        import tempfile
        
        video = db.query(InterviewVideo).filter(InterviewVideo.id == video_id).first()
        if not video or not video.video_url:
            return

        # Skip if already processed successfully
        if (video.transcription and video.expression_analysis and 
            video.transcription != "No clear speech detected" and 
            not video.expression_analysis.startswith("No face") and
            not video.expression_analysis.startswith("Unable to")):
            return

        print(f"\n{'='*60}")
        print(f"🎙️ AI Processing Video {video_id} (Q{video.question_index + 1})")
        print(f"{'='*60}")
        
        # 1. Setup FFmpeg
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
            os.environ["FFMPEG_BINARY"] = ffmpeg_exe
            print(f"  ℹ️ Using ffmpeg from {ffmpeg_exe}")
        except Exception as fe:
            print(f"⚠️ FFmpeg setup: {fe}")

        # 2. Get video file (local or download)
        video_path = video.video_url
        tmp_path = None
        
        if video_path.startswith('http'):
            # Download from URL
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
                resp = requests.get(video_path, stream=True, timeout=30)
                if resp.status_code == 200:
                    for chunk in resp.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                    tmp_path = tmp.name
                    print(f"✅ Video downloaded ({os.path.getsize(tmp_path)} bytes)")
                else:
                    print(f"❌ Download failed: {resp.status_code}")
                    return
        else:
            # Use local file
            if not os.path.exists(video_path):
                print(f"❌ Video file not found: {video_path}")
                return
            tmp_path = video_path
            print(f"✅ Using local video: {video_path} ({os.path.getsize(tmp_path)} bytes)")

        try:
            # 3. Extract and ENHANCE audio
            print(f"\n📊 AUDIO PROCESSING")
            audio_tmp_path = tmp_path.replace(".webm", ".wav")
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            
            ffmpeg_cmd = [ffmpeg_exe, '-i', tmp_path, '-vn', '-acodec', 'pcm_s16le', 
                         '-ar', '16000', '-ac', '1', '-y', audio_tmp_path]
            
            try:
                subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=60)
                print(f"  ✅ Audio extracted ({os.path.getsize(audio_tmp_path)} bytes)")
                
                # Apply audio enhancement if available
                if AUDIO_ENHANCEMENT_AVAILABLE:
                    print(f"  🔧 Applying audio enhancements...")
                    try:
                        process_audio_pipeline(audio_tmp_path)
                        print(f"  ✅ Audio enhanced")
                    except Exception as ae:
                        print(f"  ⚠️ Enhancement skipped: {ae}")
            except subprocess.CalledProcessError as e:
                print(f"  ⚠️ Audio extraction failed, using video")
                audio_tmp_path = tmp_path

            # 4. Faster-Whisper Transcription (with enhanced audio)
            print(f"\n🎤 TRANSCRIPTION")
            model = get_whisper_model()
            # Faster-Whisper returns segments and info
            segments, info = model.transcribe(audio_tmp_path, language='en')
            transcription_text = "".join([segment.text for segment in segments]).strip()
            
            # Clean transcription
            transcription_text = re.sub(r'\s+', ' ', transcription_text)
            transcription_text = ''.join(c for c in transcription_text if c.isprintable() or c in '.,!?')
            transcription_text = transcription_text.strip()
            
            if not transcription_text or len(transcription_text) < 5:
                print(f"  ❌ Empty transcription")
                video.transcription = "No clear speech detected"
            else:
                video.transcription = transcription_text
                print(f"  ✅ Transcribed: {transcription_text[:60]}...")
            
            db.commit()
            
            # Clean audio file
            if audio_tmp_path != tmp_path and os.path.exists(audio_tmp_path):
                try:
                    os.remove(audio_tmp_path)
                except:
                    pass

            # 5. Advanced Face Detection & Expression Analysis
            print(f"\n👁️ EXPRESSION ANALYSIS")
            try:
                # Try advanced detection first
                if FACE_DETECTION_AVAILABLE:
                    try:
                        print(f"  🔍 Using advanced face detection...")
                        result = simple_face_detection(tmp_path, max_frames=20)
                        
                        if result['face_detected']:
                            # Get expression estimate
                            expression = estimate_expressions_from_video(tmp_path, max_frames=15)
                            video.expression_analysis = expression
                            print(f"  ✅ Face found ({result['confidence']:.0%}): {expression}")
                        else:
                            print(f"  ⚠️ Advanced detection: No face found")
                            # Fallback to basic detection
                            video.expression_analysis = "No face detected in video"
                    except Exception as ae:
                        print(f"  ⚠️ Advanced detection failed: {ae}")
                        raise  # Fall through to basic detection
                else:
                    raise ImportError("Advanced detection not available")
                    
            except Exception as e:
                # Fallback: Basic face detection
                print(f"  🔄 Fallback to basic face detection...")
                try:
                    cap = cv2.VideoCapture(tmp_path)
                    if not cap.isOpened():
                        video.expression_analysis = "Video error"
                    else:
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        face_cascade = cv2.CascadeClassifier(
                            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                        )
                        
                        face_found = False
                        frame_indices = np.linspace(0, total_frames - 1, min(20, total_frames), dtype=int)
                        
                        for idx in frame_indices:
                            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                            ret, frame = cap.read()
                            if not ret:
                                continue
                            
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            faces = face_cascade.detectMultiScale(gray, 1.05, 4, minSize=(20, 20))
                            
                            if len(faces) > 0:
                                face_found = True
                                break
                        
                        cap.release()
                        
                        if face_found:
                            video.expression_analysis = "Face detected - Professional appearance 😐"
                            print(f"  ✅ Face detected (basic)")
                        else:
                            video.expression_analysis = "No face detected in video"
                            print(f"  ❌ No face found")
                            
                except Exception as be:
                    video.expression_analysis = "Face detection failed"
                    print(f"  ❌ Basic detection error: {be}")

            # 6. Ollama AI Evaluation
            print(f"\n🤖 AI EVALUATION")
            if video.transcription and video.question_text:
                try:
                    prompt = f"""You are a strict technical interviewer evaluating if a candidate's answer is correct for the given question.

Question: "{video.question_text}"
Candidate's Answer: "{video.transcription}"
Facial Expression: "{video.expression_analysis}"

First, check if the candidate's answer is technically correct and actually answers the specific question asked.
Provide your final evaluation in EXACTLY this format:
Score: [X]/10 - [One sentence feedback stating if the answer is correct or incorrect, and exactly why.]"""
                    
                    resp = requests.post(
                        "http://127.0.0.1:11434/api/generate",
                        json={"model": "llama3", "prompt": prompt, "stream": False, "options": {"temperature": 0.4}},
                        timeout=60
                    )
                    if resp.status_code == 200:
                        eval_text = resp.json().get("response", "").strip()
                        eval_text = eval_text.replace('\n', ' ').replace('\r', '')
                        video.ai_feedback = eval_text
                        print(f"  ✅ {eval_text[:60]}...")
                    else:
                        video.ai_feedback = "Score: N/A - AI service error"
                        print(f"  ⚠️ AI evaluation failed ({resp.status_code})")
                except Exception as oe:
                    video.ai_feedback = "Score: N/A - Connection error"
                    print(f"  ⚠️ Ollama error: {oe}")
            else:
                video.ai_feedback = "Score: 0/10 - No answer provided"

            db.commit()
            print(f"\n✨ Processing complete for Q{video.question_index + 1}\n")

        finally:
            # Cleanup - only remove temp files (downloaded videos), not local videos
            if tmp_path and video_path.startswith('http') and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            # Remove temp audio files
            if audio_tmp_path != tmp_path and os.path.exists(audio_tmp_path):
                try:
                    os.remove(audio_tmp_path)
                except:
                    pass
                
    except Exception as e:
        print(f"❌ Error processing video {video_id}: {e}")
    finally:
        db.close()


def download_video_to_temp_file(video_url: str) -> str:
    """Download a video URL to a temporary file or validate a local file path."""
    if video_url.startswith('http://') or video_url.startswith('https://'):
        suffix = os.path.splitext(video_url.split('?')[0])[1] or '.webm'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            resp = requests.get(video_url, stream=True, timeout=30)
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name

    if os.path.exists(video_url):
        return video_url

    raise FileNotFoundError(f"Video path not found: {video_url}")


def transcribe_video_only_task(video_id: int):
    """Transcribe only the audio from a video URL and save the text to the database."""
    import subprocess
    import imageio_ffmpeg

    db = SessionLocal()
    tmp_path = None
    downloaded_temp = False

    try:
        video = db.query(InterviewVideo).filter(InterviewVideo.id == video_id).first()
        if not video or not video.video_url:
            return

        if video.transcription and not video.transcription.startswith("Transcription failed"):
            return

        try:
            tmp_path = download_video_to_temp_file(video.video_url)
            downloaded_temp = video.video_url.startswith('http://') or video.video_url.startswith('https://')
        except Exception as e:
            video.transcription = f"Transcription failed: {e}"
            video.expression_analysis = "skipped"
            video.ai_feedback = "skipped"
            db.commit()
            return

        audio_tmp_path = os.path.splitext(tmp_path)[0] + ".wav"
        try:
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            ffmpeg_cmd = [
                ffmpeg_exe,
                '-i', tmp_path,
                '-vn',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-y',
                audio_tmp_path
            ]
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=90)
            audio_source = audio_tmp_path
        except Exception as e:
            print(f"⚠️ Audio extraction failed for video {video_id}: {e}")
            audio_source = tmp_path

        try:
            model = get_whisper_model()
            result = model.transcribe(audio_source, language='en', fp16=False, verbose=False)
            transcription_text = result.get('text', '').strip()
            transcription_text = re.sub(r'\s+', ' ', transcription_text)
            transcription_text = ''.join(c for c in transcription_text if c.isprintable() or c in '.,!?')
            transcription_text = transcription_text.strip()

            if transcription_text and len(transcription_text) >= 2:
                video.transcription = transcription_text
            else:
                video.transcription = "No clear speech detected"

            video.expression_analysis = "skipped"
            video.ai_feedback = "skipped"
            db.commit()
            print(f"✅ Transcription saved for video {video_id}")

        except Exception as e:
            video.transcription = f"Transcription failed: {e}"
            video.expression_analysis = "skipped"
            video.ai_feedback = "skipped"
            db.commit()
            print(f"❌ Whisper transcription error for video {video_id}: {e}")

    finally:
        if downloaded_temp and tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        if tmp_path and os.path.exists(audio_tmp_path) and audio_tmp_path != tmp_path:
            try:
                os.remove(audio_tmp_path)
            except Exception:
                pass
        db.close()


@app.post("/upload-video-url")
async def upload_video_url(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    video_url: str = Form(...),
    question_index: int = Form(default=0),
    question_text: str = Form(default=""),
    session_id: str = Form(default="url_session"),
    db: Session = Depends(get_db),
):
    """Save a video URL and queue audio-only transcription into the database."""
    candidate = db.query(Candidate).filter(Candidate.email == email).first()
    if not candidate:
        return {"error": "Candidate not found"}

    from datetime import datetime
    record = InterviewVideo(
        candidate_id=candidate.id,
        session_id=session_id,
        question_index=question_index,
        question_text=question_text,
        video_url=video_url,
        public_id=None,
        transcription=None,
        expression_analysis="skipped",
        ai_feedback="skipped",
        created_at=datetime.utcnow().isoformat(),
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    background_tasks.add_task(transcribe_video_only_task, record.id)

    return {
        "message": "Video URL saved and transcription queued",
        "video_id": record.id,
        "video_url": video_url,
        "question_index": question_index,
        "candidate_id": candidate.id,
    }


def transcribe_candidate_videos(candidate_id: int):
    """Background task to catch up on any unprocessed videos (fallback for batch)"""
    db = SessionLocal()
    try:
        videos = db.query(InterviewVideo).filter(
            InterviewVideo.candidate_id == candidate_id,
            (InterviewVideo.transcription == None)
        ).all()
        for v in videos:
            transcribe_video_only_task(v.id)
    finally:
        db.close()

@app.post("/reprocess-missing")
def reprocess_missing_videos(
    background_tasks: BackgroundTasks,
    email: str = Form(default=None),
    db: Session = Depends(get_db)
):
    """Manually queue all missing video processing tasks."""
    query = db.query(InterviewVideo).filter(
        (InterviewVideo.transcription == None)
    )
    if email:
        candidate = db.query(Candidate).filter(Candidate.email == email).first()
        if not candidate:
            return {"error": "Candidate not found"}
        query = query.filter(InterviewVideo.candidate_id == candidate.id)

    videos = query.all()
    for video in videos:
        background_tasks.add_task(transcribe_video_only_task, video.id)

    return {
        "message": f"Queued {len(videos)} missing video(s) for reprocessing",
        "video_ids": [video.id for video in videos],
    }

@app.post("/finish-interview")
async def finish_interview(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    """Trigger background video transcription and AI analysis when interview is finished"""
    candidate = db.query(Candidate).filter(Candidate.email == email).first()
    if not candidate:
        return {"error": "Candidate not found"}
        
    # Get all unprocessed videos
    videos = db.query(InterviewVideo).filter(
        InterviewVideo.candidate_id == candidate.id,
        (InterviewVideo.transcription == None)
    ).all()
    
    print(f"🚀 Queueing {len(videos)} video(s) for FULL AI processing for {email}")
    
    # Process each video in background (one by one using queue)
    for video in videos:
        background_tasks.add_task(process_single_video_task, video.id)
    
    return {"message": f"Full AI processing started for {len(videos)} video(s)"}


@app.delete("/delete-interview-data")
def delete_interview_data_endpoint(
    email: str,
    db: Session = Depends(get_db)
):
    """
    DELETE ENDPOINT: Manually delete ALL interview data for a candidate by email.
    
    This deletes:
    • Questions (question_text)
    • Transcriptions/Answers (extracted voice-to-text from transcription column)
    • Expressions (expression_analysis)
    • AI Feedback (ai_feedback)
    • Videos from Cloudinary
    • Database records
    
    Usage:
        DELETE /delete-interview-data?email=candidate@example.com
    
    Returns: Success/failure status with details
    """
    try:
        # Find candidate by email
        candidate = db.query(Candidate).filter(Candidate.email == email).first()
        if not candidate:
            return {"error": f"Candidate not found: {email}", "success": False}
        
        # Find all interview videos for this candidate
        videos = db.query(InterviewVideo).filter(
            InterviewVideo.candidate_id == candidate.id
        ).all()
        
        if not videos:
            return {
                "message": f"No interview data found for {email}",
                "email": email,
                "success": True,
                "deleted_count": 0
            }
        
        print(f"\n🗑️ MANUAL DELETE REQUEST for {email}")
        print(f"   Found {len(videos)} interview records to delete")
        
        deleted_count = 0
        errors = []
        
        # Process each video one by one
        for i, video in enumerate(videos, 1):
            try:
                print(f"\n   [{i}/{len(videos)}] Deleting Video ID {video.id}:")
                
                # Log what's being deleted
                if video.question_text:
                    print(f"       • Question: {video.question_text[:50]}...")
                if video.transcription:
                    print(f"       • Answer (transcription): {video.transcription[:50]}...")
                if video.expression_analysis:
                    print(f"       • Expressions: {video.expression_analysis[:50]}...")
                if video.ai_feedback:
                    print(f"       • AI Feedback: {video.ai_feedback[:50]}...")
                
                # Delete from Cloudinary
                if video.public_id:
                    try:
                        print(f"       • Cloudinary Video ID: {video.public_id}")
                        cloudinary.uploader.destroy(video.public_id, resource_type="video")
                    except Exception as ce:
                        error_msg = f"Cloudinary deletion issue: {str(ce)[:100]}"
                        print(f"       ⚠️ {error_msg}")
                        errors.append(error_msg)
                
                # Delete from database
                db.delete(video)
                deleted_count += 1
                print(f"       ✓ Deleted from database")
                
            except Exception as e:
                error_msg = f"Video {video.id} error: {str(e)[:100]}"
                print(f"       ❌ {error_msg}")
                errors.append(error_msg)
        
        # Commit all deletions
        db.commit()
        
        print(f"\n✅ Deletion complete: {deleted_count}/{len(videos)} records deleted")
        
        return {
            "success": True,
            "message": f"Successfully deleted {deleted_count} interview records for {email}",
            "email": email,
            "deleted_count": deleted_count,
            "total_videos": len(videos),
            "deleted_items": {
                "questions": "Cleared ✓",
                "transcriptions_answers": "Cleared ✓",
                "expressions": "Cleared ✓",
                "ai_feedback": "Cleared ✓",
                "cloudinary_videos": "Deleted ✓",
                "database_records": f"{deleted_count} deleted ✓"
            },
            "errors": errors if errors else None
        }
        
    except Exception as e:
        print(f"❌ Deletion error: {e}")
        db.rollback()
        return {
            "success": False,
            "error": f"Deletion failed: {str(e)}",
            "email": email
        }


@app.get("/interview-report")
def get_interview_report(email: str, session_id: str = None, db: Session = Depends(get_db)):
    """Fetch the final processed report (transcriptions and expressions) for a candidate."""
    candidate = db.query(Candidate).filter(Candidate.email == email).first()
    if not candidate:
        return {"error": "Candidate not found"}
    
    # For now, use a workaround: if session_id is provided, filter by it
    # If session_id column doesn't exist, we'll get all videos and filter in memory
    try:
        if session_id:
            # Try to filter by session_id if column exists
            query = db.query(InterviewVideo).filter(InterviewVideo.candidate_id == candidate.id)
            # Check if session_id column exists by trying the filter
            try:
                videos = query.filter(InterviewVideo.session_id == session_id).order_by(InterviewVideo.question_index).all()
            except:
                # Column doesn't exist, filter in memory
                all_videos = query.order_by(InterviewVideo.question_index).all()
                videos = [v for v in all_videos if getattr(v, 'session_id', 'legacy') == session_id]
        else:
            # Get latest session - try to find videos with the same session pattern
            query = db.query(InterviewVideo).filter(InterviewVideo.candidate_id == candidate.id)
            all_videos = query.order_by(InterviewVideo.created_at.desc()).all()
            
            if all_videos:
                # Group by session (if session_id exists) or use latest videos
                try:
                    latest_session = getattr(all_videos[0], 'session_id', 'legacy')
                    videos = [v for v in all_videos if getattr(v, 'session_id', latest_session) == latest_session][:5]
                except:
                    # No session_id column, just take the 5 most recent videos
                    videos = all_videos[:5]
            else:
                videos = []
    except Exception as e:
        print(f"Database query error: {e}")
        # Fallback: get all videos for this candidate
        videos = db.query(InterviewVideo).filter(InterviewVideo.candidate_id == candidate.id).order_by(InterviewVideo.question_index).all()
    
    # Enforce strict 5-question cap on results
    videos = videos[:5]

    results = []
    all_done = True

    if len(videos) < 5:
        all_done = False

    for v in videos:
        if not v.transcription or not v.expression_analysis or not v.ai_feedback:
            all_done = False
        results.append({
            "question": v.question_text,
            "transcription": v.transcription or "Extracting text...",
            "expression": v.expression_analysis or "Analyzing expressions...",
            "feedback": getattr(v, "ai_feedback", "Evaluating answer...")
        })

    return {
        "status": "completed" if all_done else "processing",
        "total_questions": len(results),
        "results": results
    }

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)