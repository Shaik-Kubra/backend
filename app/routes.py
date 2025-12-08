from flask import Blueprint, request, jsonify
from .models import supabase
import google.generativeai as genai
from .config import Config

main = Blueprint('main', __name__)

# Configure Gemini
if Config.GEMINI_API_KEY:
    genai.configure(api_key=Config.GEMINI_API_KEY)

# --- 1. ROOT CHECK ---
@main.route('/')
def home():
    return "✅ Backend server is running! The API is ready."

# --- 2. REGISTER STUDENT (Updated for your specific schema) ---
@main.route('/api/register-student', methods=['POST'])
def register_student():
    data = request.json
    try:
        # NOTE: We removed 'student_reg_no' because your table doesn't have it.
        student_data = {
            "id": data.get('id'),
            "email": data.get('email'),
            "full_name": data.get('full_name'),
            "department": data.get('department')
        }
        
        # Insert into Supabase
        supabase.table('students').insert(student_data).execute()
        return jsonify({"message": "Student created successfully!"}), 201
    except Exception as e:
        print(f"Error registering student: {e}") # Print error to terminal for debugging
        return jsonify({"error": str(e)}), 500

# --- 3. SUBMIT COMPLAINT ---
@main.route('/api/submit-complaint', methods=['POST'])
def submit_complaint():
    data = request.json
    faculty_email = data.get('faculty_email')
    
    # 1. Check if Faculty exists
    faculty_response = supabase.table('faculty').select('id').eq('email', faculty_email).execute()
    
    # If faculty not found, return error
    if not faculty_response.data:
        return jsonify({"error": f"Faculty with email '{faculty_email}' not found."}), 404
        
    faculty_id = faculty_response.data[0]['id']

    # 2. Prepare Complaint Data
    complaint_data = {
        "student_id": data.get('student_id'),
        "faculty_email": faculty_email,
        "faculty_id": faculty_id,
        "description": data.get('description'),
        "status": "Pending"
        # We are leaving 'title' empty as it's optional in your schema
    }
    
    try:
        supabase.table('complaints').insert(complaint_data).execute()
        return jsonify({"message": "Complaint sent!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 4. GET HISTORY ---
@main.route('/api/my-complaints/<student_id>', methods=['GET'])
def get_my_complaints(student_id):
    try:
        # Fetch complaints AND join with the responses table
        # syntax: table_name(columns)
        response = supabase.table('complaints')\
            .select('description, status, created_at, complaint_responses(response_message)')\
            .eq('student_id', student_id)\
            .execute()
            
        formatted_data = []
        for item in response.data:
            # Default answer
            answer_text = "Waiting for response..."
            
            # Check if there is a response in the joined list
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

# --- 5. ASK GEMINI ---
# In server/app/routes.py

@main.route('/api/ask-ai', methods=['POST'])
def ask_ai():
    data = request.json
    question = data.get('question')
    print(f"📝 User asked: {question}") # Log the question

    try:
        # Check if key is loaded
        if not Config.GEMINI_API_KEY:
            print("❌ ERROR: Gemini API Key is Missing!")
            return jsonify({"error": "API Key missing"}), 500

        model = genai.GenerativeModel('gemini-flash-latest')
        response = model.generate_content(question)
        
        print("✅ Gemini replied successfully")
        return jsonify({"answer": response.text})
        
    except Exception as e:
        print(f"🔥 CRASH ERROR: {str(e)}") # <--- THIS PRINTS THE REAL ERROR
        return jsonify({"error": str(e)}), 500
    

# ... (Keep all your existing Student and AI routes above this) ...

# --- 6. REGISTER FACULTY (Matches FacultySignup.js) ---
@main.route('/api/register-faculty', methods=['POST'])
def register_faculty():
    data = request.json
    try:
        faculty_data = {
            "id": data.get('id'), # Auth ID from Supabase
            "full_name": data.get('full_name'),
            "email": data.get('email'),
            "department": data.get('department'),
            # Note: Ensure your Supabase 'faculty' table has these columns.
            # If you haven't added 'fid' or 'phone' to the DB yet, remove them here.
            # "fid": data.get('fid'), 
            # "phone": data.get('phone') 
        }
        
        supabase.table('faculty').insert(faculty_data).execute()
        return jsonify({"message": "Faculty profile created!"}), 201
    except Exception as e:
        print(f"Error registering faculty: {e}")
        return jsonify({"error": str(e)}), 500


# --- 7. GET FACULTY COMPLAINTS (Matches FacultyDashboard.js) ---
@main.route('/api/faculty/complaints/<faculty_id>', methods=['GET'])
def get_faculty_complaints(faculty_id):
    try:
        # Fetch all complaints assigned to this faculty member
        response = supabase.table('complaints')\
            .select('*')\
            .eq('faculty_id', faculty_id)\
            .order('created_at', desc=True)\
            .execute()
            
        return jsonify(response.data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- 8. SEND REPLY (Matches ReplyModal.js) ---
@main.route('/api/faculty/reply', methods=['POST'])
def faculty_reply():
    data = request.json
    complaint_id = data.get('complaint_id')
    faculty_id = data.get('faculty_id')
    message = data.get('response_message')

    try:
        # Step A: Save the response in the 'complaint_responses' table
        response_data = {
            "complaint_id": complaint_id,
            "faculty_id": faculty_id,
            "response_message": message
        }
        supabase.table('complaint_responses').insert(response_data).execute()

        # Step B: Update the main complaint status to 'Resolved'
        supabase.table('complaints')\
            .update({"status": "Resolved"})\
            .eq('id', complaint_id)\
            .execute()

        return jsonify({"message": "Reply sent and status updated!"}), 201
    except Exception as e:
        print(f"Error sending reply: {e}")
        return jsonify({"error": str(e)}), 500
    
# --- 9. GET STUDENT PROFILE (Fixes the wrong data issue) ---
@main.route('/api/student/profile/<user_id>', methods=['GET'])
def get_student_profile(user_id):
    try:
        # Fetch student details from Supabase using the Auth ID
        response = supabase.table('students').select('*').eq('id', user_id).execute()
        
        if response.data and len(response.data) > 0:
            return jsonify(response.data[0]), 200
        else:
            return jsonify({"error": "Student profile not found"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 10. GET FACULTY PROFILE ---
@main.route('/api/faculty/profile/<user_id>', methods=['GET'])
def get_faculty_profile(user_id):
    try:
        # Fetch faculty details from Supabase using the Auth ID
        response = supabase.table('faculty').select('*').eq('id', user_id).execute()
        
        if response.data and len(response.data) > 0:
            return jsonify(response.data[0]), 200
        else:
            return jsonify({"error": "Faculty profile not found"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500  
    
# --- 11. UPDATE STUDENT PROFILE ---
@main.route('/api/student/profile/<user_id>', methods=['PUT'])
def update_student_profile(user_id):
    data = request.json
    try:
        # Prepare the data to update
        update_data = {
            "full_name": data.get('name'),
            "email": data.get('email'),
            "department": data.get('department'),
            # "student_reg_no": data.get('id') # Usually ID numbers are not editable, but uncomment if needed
        }
        
        # Update the row in Supabase
        response = supabase.table('students').update(update_data).eq('id', user_id).execute()
        
        return jsonify({"message": "Student profile updated successfully!"}), 200
    except Exception as e:
        print(f"Error updating student: {e}")
        return jsonify({"error": str(e)}), 500


# --- 12. UPDATE FACULTY PROFILE ---
@main.route('/api/faculty/profile/<user_id>', methods=['PUT'])
def update_faculty_profile(user_id):
    data = request.json
    try:
        # Prepare the data to update
        update_data = {
            "full_name": data.get('name'),
            "email": data.get('email'),
            "phone": data.get('phone'),
            "department": data.get('department')
            # FID is usually not editable
        }
        
        # Update the row in Supabase
        response = supabase.table('faculty').update(update_data).eq('id', user_id).execute()
        
        return jsonify({"message": "Faculty profile updated successfully!"}), 200
    except Exception as e:
        print(f"Error updating faculty: {e}")
        return jsonify({"error": str(e)}), 500