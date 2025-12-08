import os
import glob
import google.generativeai as genai
from flask import Blueprint, request, jsonify
from .models import supabase
from .config import Config

main = Blueprint('main', __name__)

# --- CONFIGURATION ---
if Config.GEMINI_API_KEY:
    genai.configure(api_key=Config.GEMINI_API_KEY)

# --- GLOBAL STORAGE FOR UPLOADED FILES (AI MEMORY) ---
# We store uploaded file references here so we don't re-upload them every time
knowledge_base = []

def load_college_data():
    """Scans the 'documents/college_data' folder and uploads files to Gemini."""
    global knowledge_base
    
    # If we already loaded data, skip re-uploading to save time/bandwidth
    if len(knowledge_base) > 0:
        return

    print("📂 Scanning 'college_data' folder...")
    
    # 1. Define path to your documents
    # Assumes your folder is at: server/documents/college_data
    folder_path = os.path.join(os.path.dirname(__file__), '../documents/college_data')
    
    # 2. Find all relevant files
    extensions = ['*.pdf', '*.jpg', '*.jpeg', '*.png', '*.txt']
    files_to_upload = []
    
    if not os.path.exists(folder_path):
        print(f"❌ Error: Folder not found at {folder_path}")
        print("   Please create 'server/documents/college_data' and put your files there.")
        return

    for ext in extensions:
        files_to_upload.extend(glob.glob(os.path.join(folder_path, ext)))

    if not files_to_upload:
        print("⚠️ No files found in college_data folder.")
        return

    print(f"found {len(files_to_upload)} files. Uploading to Gemini (this may take a minute)...")

    # 3. Upload files to Google
    for file_path in files_to_upload:
        try:
            uploaded_file = genai.upload_file(file_path)
            knowledge_base.append(uploaded_file)
            print(f"   ✅ Uploaded: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"   ❌ Failed: {os.path.basename(file_path)} - {e}")

    print(f"🚀 Knowledge Base Ready! ({len(knowledge_base)} documents loaded)")


# --- 1. ROOT CHECK ---
@main.route('/')
def home():
    return "✅ Backend server is running! The API is ready."

# --- 2. ASK GEMINI (RAG / FILE SEARCH) ---
@main.route('/api/ask-ai', methods=['POST'])
def ask_ai():
    data = request.json
    question = data.get('question')
    print(f"📝 User asked: {question}")

    try:
        # Check API Key
        if not Config.GEMINI_API_KEY:
            return jsonify({"error": "Gemini API Key missing"}), 500

        # 1. Ensure data is loaded (Lazy Loading)
        if not knowledge_base:
            load_college_data()
            
        # 2. Configure Model (Use Flash for large context)
        # Use the model name you confirmed earlier (e.g., 'gemini-1.5-flash' or 'gemini-flash-latest')
        model = genai.GenerativeModel('gemini-flash-latest')
        # 3. Create the Prompt with Files
        chat_content = [
            "You are the official AI Assistant for RGUKT (Rajiv Gandhi University of Knowledge Technologies).",
            "Use the provided files (PDFs, Images, Text) to answer the student's question accurately.",
            "If the answer is found in the 'mess_menu' image, read the table row/column carefully.",
            "If the answer is not in these documents, strictly say 'I don't have that information in my internal records.'",
            "Question: " + question
        ]
        
        # Attach the uploaded files to the prompt
        if knowledge_base:
            chat_content.extend(knowledge_base)
        else:
            chat_content.append("(No internal documents available. Answer using general knowledge if safe.)")

        # 4. Generate Response
        response = model.generate_content(chat_content)
        
        print("✅ Gemini replied successfully")
        return jsonify({"answer": response.text})
        
    except Exception as e:
        print(f"🔥 CRASH ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 500


# --- 3. REGISTER STUDENT (Updated for reg_id) ---
@main.route('/api/register-student', methods=['POST'])
def register_student():
    data = request.json
    try:
        student_data = {
            "id": data.get('id'),         # Auth UUID
            "email": data.get('email'),
            "full_name": data.get('full_name'),
            "department": data.get('department'),
            # MAP THE FRONTEND ID TO YOUR NEW DATABASE COLUMN
            "reg_id": data.get('student_reg_no') 
        }
        supabase.table('students').insert(student_data).execute()
        return jsonify({"message": "Student created successfully!"}), 201
    except Exception as e:
        print(f"Error registering student: {e}")
        return jsonify({"error": str(e)}), 500

# --- 4. SUBMIT COMPLAINT ---
@main.route('/api/submit-complaint', methods=['POST'])
def submit_complaint():
    data = request.json
    faculty_email = data.get('faculty_email')
    
    # Check Faculty
    faculty_response = supabase.table('faculty').select('id').eq('email', faculty_email).execute()
    if not faculty_response.data:
        return jsonify({"error": f"Faculty with email '{faculty_email}' not found."}), 404
        
    faculty_id = faculty_response.data[0]['id']

    complaint_data = {
        "student_id": data.get('student_id'),
        "faculty_email": faculty_email,
        "faculty_id": faculty_id,
        "description": data.get('description'),
        "status": "Pending"
    }
    
    try:
        supabase.table('complaints').insert(complaint_data).execute()
        return jsonify({"message": "Complaint sent!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 5. GET STUDENT HISTORY ---
@main.route('/api/my-complaints/<student_id>', methods=['GET'])
def get_my_complaints(student_id):
    try:
        response = supabase.table('complaints')\
            .select('description, status, created_at, complaint_responses(response_message)')\
            .eq('student_id', student_id)\
            .execute()
            
        formatted_data = []
        for item in response.data:
            answer_text = "Waiting for response..."
            if item.get('complaint_responses') and len(item['complaint_responses']) > 0:
                answer_text = item['complaint_responses'][0]['response_message']
            
            formatted_data.append({
                "question": item['description'],
                "answer": answer_text,
                "status": item['status'],
                "date": item['created_at']
            })
            
        return jsonify(formatted_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 6. REGISTER FACULTY ---
@main.route('/api/register-faculty', methods=['POST'])
def register_faculty():
    data = request.json
    try:
        faculty_data = {
            "id": data.get('id'),
            "full_name": data.get('full_name'),
            "email": data.get('email'),
            "department": data.get('department')
            # "fid": data.get('fid'),  # Uncomment if column exists in DB
            # "phone": data.get('phone') # Uncomment if column exists in DB
        }
        supabase.table('faculty').insert(faculty_data).execute()
        return jsonify({"message": "Faculty profile created!"}), 201
    except Exception as e:
        print(f"Error registering faculty: {e}")
        return jsonify({"error": str(e)}), 500

# --- 7. GET FACULTY COMPLAINTS (With Student Details) ---
@main.route('/api/faculty/complaints/<faculty_id>', methods=['GET'])
def get_faculty_complaints(faculty_id):
    try:
        # Joined query to get student details
        response = supabase.table('complaints')\
            .select('*, students(full_name, student_reg_no)')\
            .eq('faculty_id', faculty_id)\
            .order('created_at', desc=True)\
            .execute()
            
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 8. SEND FACULTY REPLY ---
@main.route('/api/faculty/reply', methods=['POST'])
def faculty_reply():
    data = request.json
    complaint_id = data.get('complaint_id')
    faculty_id = data.get('faculty_id')
    message = data.get('response_message')

    try:
        # Save response
        response_data = {
            "complaint_id": complaint_id,
            "faculty_id": faculty_id,
            "response_message": message
        }
        supabase.table('complaint_responses').insert(response_data).execute()

        # Update status
        supabase.table('complaints')\
            .update({"status": "Resolved"})\
            .eq('id', complaint_id)\
            .execute()

        return jsonify({"message": "Reply sent!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 9. GET STUDENT PROFILE ---
@main.route('/api/student/profile/<user_id>', methods=['GET'])
def get_student_profile(user_id):
    try:
        response = supabase.table('students').select('*').eq('id', user_id).execute()
        if response.data:
            return jsonify(response.data[0]), 200
        return jsonify({"error": "Profile not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 10. GET FACULTY PROFILE ---
@main.route('/api/faculty/profile/<user_id>', methods=['GET'])
def get_faculty_profile(user_id):
    try:
        response = supabase.table('faculty').select('*').eq('id', user_id).execute()
        if response.data:
            return jsonify(response.data[0]), 200
        return jsonify({"error": "Profile not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 11. UPDATE STUDENT PROFILE ---
@main.route('/api/student/profile/<user_id>', methods=['PUT'])
def update_student_profile(user_id):
    data = request.json
    try:
        update_data = {
            "full_name": data.get('name'),
            "email": data.get('email'),
            "department": data.get('department')
        }
        supabase.table('students').update(update_data).eq('id', user_id).execute()
        return jsonify({"message": "Updated!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 12. UPDATE FACULTY PROFILE ---
@main.route('/api/faculty/profile/<user_id>', methods=['PUT'])
def update_faculty_profile(user_id):
    data = request.json
    try:
        update_data = {
            "full_name": data.get('name'),
            "email": data.get('email'),
            "department": data.get('department'),
            "phone": data.get('phone') # Ensure this column exists in DB
        }
        supabase.table('faculty').update(update_data).eq('id', user_id).execute()
        return jsonify({"message": "Updated!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500