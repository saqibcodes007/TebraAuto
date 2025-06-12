# Tebra Automation Tool - Flask Web Application

## 1. Project Overview

**Name:** Tebra Automation Tool
**Purpose:** This Flask web application automates various tasks within the Tebra Practice Management System (PMS) by interacting with the Tebra SOAP API. It aims to streamline workflows related to patient data, payments, and charge entry using an asynchronous processing model for improved responsiveness.
**Origin:** The application is an enhanced web-based version of an original Python script (`tebra_automation_tool_v2.py`) designed for Google Colab.

**Core Functionalities (Asynchronous Workflow):**
* **File Upload & Task Initiation:**
    * User uploads an Excel file containing patient and service information via the web UI.
    * The backend (`/api/process`) quickly validates the request, saves the file, starts a background processing task, and immediately returns a `task_id` to the UI.
* **Background Processing (executed by a thread in the backend):**
    * **Patient and Insurance Verification (Phase 1):** For each relevant row, fetches patient details (Name, DOB) and primary active insurance information (Insurance Name, Insurance ID, Insurance Status) from Tebra using Patient ID and Date of Service (DOS).
    * **Payment Posting (Phase 2):** If payment details are provided, posts these payments to Tebra.
    * **Encounter Creation & Charge Entry (Phase 3):** Rows with the same Patient ID, DOS, and Practice are grouped. For each group, creates an encounter with details like Rendering Provider, Scheduling Provider, Referring Provider, Encounter Mode, Place of Service (POS), hospitalization dates, and multiple service lines.
    * Saves the processed data (with fetched details like Patient Name, DOB, Insurance info, Encounter ID, Charge Status, Charge Amount, and any errors) to an output Excel file on the server.
    * Updates a status file indicating completion or error.
* **Status Polling (Frontend):**
    * The frontend JavaScript polls an `/api/status/<task_id>` endpoint to check the progress of the background task.
* **Results & Output Download:**
    * Once processing is complete, the UI informs the user.
    * The frontend JavaScript automatically triggers a download of the processed Excel file from a new `/api/download_processed_file/<filename>` endpoint.
    * The output Excel contains the original data enriched with fetched information and processing statuses.

## 2. Technology Stack

* **Backend:** Python 3.11 (as per Dockerfile), Flask
* **Frontend:** HTML5, CSS3, JavaScript (ES6)
* **Python Libraries:**
    * `Flask`: Web framework.
    * `pandas`: Data manipulation, Excel file reading/writing.
    * `zeep`: SOAP client for Tebra API interaction.
    * `openpyxl`: Used by pandas for reading/writing `.xlsx` files.
    * `pytz`: For timezone handling.
    * `requests`: HTTP library, underlying dependency for `zeep`.
    * `Flask-SQLAlchemy`: ORM for database interaction (currently commented out in `main.py` but present as a dependency).
    * `gunicorn`: WSGI HTTP Server for production deployment.
    * `threading`, `uuid`: Used for background task processing and generating unique task IDs in the asynchronous flow.
* **External API:** Tebra SOAP Web Services (WSDL URL: `https://webservice.kareo.com/services/soap/2.1/KareoServices.svc?singleWsdl`)

## 3. Project Structure
TebraAuto/
├── main.py                     # Flask app entry point, app initialization
├── Dockerfile                  # Instructions to build the backend Docker image
├── requirements.txt            # Python dependencies
├── static/                     # Frontend assets
│   ├── css/
│   │   └── styles.css          # Main stylesheet
│   ├── img/
│   │   └── owl-logo.png        # Logo image
│   ├── js/
│   │   └── main.js             # Frontend JavaScript logic (handles async polling)
│   └── index.html              # Main HTML page for the UI
├── src/                        # Source code directory
│   ├── init.py             # Makes 'src' a Python package
│   ├── models/
│   │   ├── init.py
│   │   └── user.py             # SQLAlchemy database models (currently minimal)
│   └── routes/
│       ├── init.py
│       └── user.py             # Defines API endpoints and core backend logic (async processing)
└── temp_files/                 # (Used locally) Stores temporary files. In Azure, /tmp is used.

* **`main.py`**: Initializes the Flask application, registers blueprints.
* **`src/routes/user.py`**: Core backend logic. Handles:
    * `/api/process` (POST): Receives file, starts background processing thread, returns `task_id`.
    * `background_task_processor()`: Function running in a thread to perform Tebra interactions and Excel generation.
    * `/api/status/<task_id>` (GET): Reports status of background task ("pending", "completed", "error").
    * `/api/download_processed_file/<filename>` (GET): Serves the processed Excel file.
    * Interaction with Tebra SOAP API (`zeep`).
    * File validation and Tebra entity ID caching.
* **`static/js/main.js`**: Handles client-side logic:
    * DOM manipulation, form validation, AJAX call to `/api/process`.
    * Receives `task_id` and polls `/api/status/<task_id>`.
    * Updates UI with progress/status.
    * Initiates file download from `/api/download_processed_file/<filename>` upon completion.
* **`temp_files/` or `/tmp/`**: The `UPLOAD_FOLDER` logic in `user.py` uses `/tmp` if available (like in Azure Container Apps), otherwise defaults to `temp_files` for local development. This directory stores the initially uploaded file, status files (`<task_id>.status`), and the final processed Excel file temporarily.

## 4. Setup and Installation

**Prerequisites:**
* Python (3.11 or higher recommended, matching Dockerfile)
* `pip` (Python package installer)
* Docker (for building and running the containerized application)

**Installation Steps (for local development/contribution):**
1.  **Clone the Repository (Example):**
    ```bash
    git clone <repository-url>
    cd TebraAuto
    ```
2.  **Create and Activate a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Environment Variables:**
    * `PORT`: (Optional for local, defaults to 5000) For compatibility with some hosting platforms.
    * `GUNICORN_TIMEOUT`: (Optional for local Gunicorn, defaults in Dockerfile to 300) Timeout for Gunicorn workers.
    * Database variables (if DB functionality is re-enabled): `DB_USERNAME`, `DB_PASSWORD`, etc.

## 5. Running the Application

1.  **Local Development Mode (Flask's built-in server):**
    From the project root directory:
    ```bash
    python main.py
    ```
    Accessible at `http://localhost:5000` (or as per `PORT` env var).

2.  **Production-like Mode (using Gunicorn, similar to Docker CMD):**
    Your `Dockerfile` uses a command like:
    ```dockerfile
    CMD gunicorn --workers 3 --timeout $GUNICORN_TIMEOUT --graceful-timeout 90 --bind "0.0.0.0:5000" --access-logfile - --error-logfile - main:app
    ```
    To run locally with Gunicorn (ensure Gunicorn is installed in your venv):
    ```bash
    # Example for macOS/Linux (set GUNICORN_TIMEOUT first)
    export GUNICORN_TIMEOUT=300 
    gunicorn --workers 3 --timeout $GUNICORN_TIMEOUT --graceful-timeout 90 --bind 0.0.0.0:5000 --access-logfile - --error-logfile - main:app
    
    # For Windows (Command Prompt):
    # set GUNICORN_TIMEOUT=300
    # gunicorn --workers 3 --timeout %GUNICORN_TIMEOUT% --graceful-timeout 90 --bind 0.0.0.0:5000 --access-logfile - --error-logfile - main:app
    
    # For Windows (PowerShell):
    # $env:GUNICORN_TIMEOUT="300"
    # gunicorn --workers 3 --timeout $env:GUNICORN_TIMEOUT --graceful-timeout 90 --bind 0.0.0.0:5000 --access-logfile - --error-logfile - main:app
    ```
    (Adjust workers, port, and timeout as needed.)

3.  **Running with Docker (Recommended for testing deployment consistency):**
    * Build the image: `docker build -t tebraauto .`
    * Run the container: `docker run -p 5000:5000 -e GUNICORN_TIMEOUT=300 tebraauto` (Maps container port 5000 to host port 5000 and sets timeout)

## 6. Application Workflow (Asynchronous)

**A. Frontend (`static/index.html`, `static/js/main.js`):**
1.  **Credentials Input & File Upload:** User provides Tebra credentials and uploads an Excel file (sheet named "Charges").
2.  **Process Initiation:** "Process Charges" button enabled when form is complete.
3.  **API Call to Backend (`/api/process`):**
    * `main.js` sends `FormData` (file, credentials) via POST.
    * Receives an immediate JSON response like `{"task_id": "unique-id", "message": "Processing started..."}` and a 202 HTTP status.
4.  **Status Polling & UI Updates:**
    * `main.js` uses the `task_id` to periodically call `/api/status/<task_id>` (e.g., every 5 seconds).
    * A progress bar simulates progress based on polling. Alerts update the user on status ("Processing...", "Error during background processing.", "Processing complete!").
5.  **Automatic Download:**
    * When `/api/status` returns `{"status": "completed", "output_filename": "...", "original_download_name": "..."}`, `main.js` automatically triggers a download by calling `/api/download_processed_file/<output_filename_from_status>`.
    * The browser handles the file download.

**B. Backend (`src/routes/user.py`):**

* **`/api/process` Endpoint (POST):**
    1.  Receives file and credentials.
    2.  Validates input.
    3.  Saves the uploaded file to a temporary server location (e.g., `/tmp/<task_id>_<original_filename>`).
    4.  Generates a unique `task_id`.
    5.  Starts a new background thread, passing it the `task_id`, path to the saved file, and credentials. The `background_task_processor` function executes in this thread.
    6.  Immediately returns a `202 Accepted` JSON response to the frontend: `{"task_id": "...", "message": "Processing started...", "status_check_url": "/api/status/..."}`.

* **`background_task_processor(input_filepath, task_id, credentials_dict, wsdl_url, original_filename_for_download)` (runs in a thread):**
    1.  Re-initializes Tebra API client for thread safety.
    2.  Reads the saved uploaded file.
    3.  Calls `validate_spreadsheet_adapted()`.
    4.  Calls `run_all_phases_processing_adapted()` which performs:
        * Row-wise Patient/Insurance data fetching (Phase 1).
        * Row-wise Payment Posting (Phase 2, if data present).
        * Grouping data for Encounter Creation (Phase 3).
        * For each group, calls `_create_encounter_for_group_and_get_details()` (Tebra API calls for encounter, status, charges).
    5.  Saves the processed DataFrame to an output Excel file named using the `task_id` in the server's temporary folder (e.g., `/tmp/Processed_<original_name>_<task_id>_<timestamp>.xlsx`).
    6.  Writes a status file (e.g., `/tmp/<task_id>.status`) with JSON indicating `{"status": "completed", "output_filename": "...", "original_download_name": "..."}` or `{"status": "error", "message": "..."}`.
    7.  Deletes the initial temporary uploaded file.

* **`/api/status/<task_id>` Endpoint (GET):**
    1.  Reads the content of the corresponding `<task_id>.status` file from the server's temporary folder.
    2.  Returns the JSON content (e.g., `{"status": "pending"}`, `{"status": "completed", ...}`, `{"status": "error", ...}`).

* **`/api/download_processed_file/<filename_on_server>` Endpoint (GET):**
    1.  Receives the server-side filename of the processed Excel (which includes the `task_id`).
    2.  Uses Flask's `send_file` to stream this file from the server's temporary folder to the user's browser.
    3.  Attempts to use a user-friendly download name derived from `original_download_name` stored in the status file.

## 7. Key Functions and Logic in `src/routes/user.py`

* **Asynchronous Task Handling:**
    * `threading`, `uuid`: For managing background tasks and unique IDs.
    * `background_task_processor()`: Core logic now runs here.
    * File-based status tracking (`<task_id>.status`).
* **API Interaction (within background task):**
    * `create_api_client_adapted()`, `build_request_header_adapted()`.
* **File Validation & Preparation (within background task):**
    * `UPLOAD_FOLDER`: Now intelligently uses `/tmp` on Azure/Linux or `temp_files` locally.
    * `validate_spreadsheet_adapted()`.
* **Tebra Entity ID Fetching & Core Logic (within background task):**
    * All `get_*_id_by_name`, `phase1_...`, `phase2_...`, `_create_encounter_...` functions are called by `run_all_phases_processing_adapted` inside the thread.
* **Helper/Utility:**
    * `display_message()`: For server console logging.

## 8. Input Excel File Format ("Charges" sheet)

The application expects an Excel file (`.xlsx` or `.xls`) containing a sheet named **"Charges"**. The columns are mapped based on the `EXPECTED_COLUMNS_CONFIG` in `src/routes/user.py`.

**Key Input Columns (refer to `EXPECTED_COLUMNS_CONFIG` for "normalized" names the tool looks for):**

* **Critical for Phase 1 (Patient/Insurance Lookup) & Grouping for Phase 3:**
    * `Patient ID`: The Tebra Patient ID.
    * `Practice`: The Practice Name as it appears in Tebra. This is also used as the Service Location context for encounters.
    * `DOS`: Date of Service.
* **Critical for Phase 3 (Encounter Creation):**
    * `Rendering Provider`: Full name of the rendering provider.
    * `Encounter Mode`: e.g., "In Office", "Telehealth".
    * `POS`: Place of Service code (e.g., "11", "02", "10").
    * `Procedures`: Procedure code (CPT/HCPCS).
    * `Units`: Number of units for the procedure.
    * `Diag 1`: Primary Diagnosis code (ICD-10).
* **Optional for Phase 3 (Encounter Creation):**
    * `CE Batch #`: Batch number for charge entry.
    * `Scheduling Provider`: Full name.
    * `Referring Provider`: Full name.
    * `Admit Date`: Hospitalization admit date.
    * `Discharge Date`: Hospitalization discharge date.
    * `Mod 1`, `Mod 2`, `Mod 3`, `Mod 4`: Procedure modifiers.
    * `Diag 2`, `Diag 3`, `Diag 4`: Additional diagnosis codes.
* **Optional for Phase 2 (Payment Posting):**
    * `PP Batch #`: Batch number for patient payments.
    * `Patient Payment`: Amount of payment.
    * `Patient Payment Source`: e.g., "CHECK", "CREDIT CARD", "EFT", "CASH".
    * `Reference Number`: Payment reference number.

**Output Columns (populated by the application in the downloaded Excel):**
* `Patient Name`
* `DOB` (Date of Birth)
* `Insurance` (Insurance Plan Name)
* `Insurance ID` (Policy Number)
* `Insurance Status` (e.g., "Active", "Inactive")
* `Charge Amount` (Total charge for the created encounter)
* `Charge Status` (Status of the created encounter, e.g., "Draft")
* `Encounter ID` (Tebra Encounter ID for created encounters)
* `Error` (Consolidated status messages and errors for each row's processing)

## 9. Error Handling and Logging

* **Backend Logging:** `display_message()` logs to server console/container logs. Errors within the background thread are logged and also written to the `<task_id>.status` file.
* **Frontend Alerts:** `main.js` shows alerts for initial `/api/process` response, polling status updates, completion, or errors.
* **API Error Responses:**
    * `/api/process` returns `202 Accepted` on success (task started) or standard HTTP errors (400, 500) on initial validation/failure.
    * `/api/status` returns status JSON.
    * `/api/download_processed_file` returns file or 404/500.
* **Output Excel "Error" Column:** Still provides row-specific feedback.

## 10. Caching Mechanism
* **Scope:** Caches are initialized locally for each background processing task (i.e., per uploaded file).
* **Cached Entities:** Tebra Practice IDs, Service Location IDs, Provider IDs for Rendering/Scheduling, Referring Provider details, and Patient Case IDs.
* **Implementation:** Python dictionaries are used within the scope of the `background_task_processor` and its called functions.

## 11. Evolution from Colab Script (`tebra_automation_tool_v2.py`)
* Web Interface, API-based Architecture, Robust Error Handling.
* **Asynchronous Processing:** The web application now uses a background thread for long-running Tebra operations to provide immediate feedback to the UI and avoid proxy timeouts. Frontend polls for status.
* Corrections & Enhancements (Referring Provider NPIs, charge calculation) are part of the core logic.

## 12. Potential Future Enhancements / Areas for Development
* **Robust Asynchronous Task Processing:** Transition from in-process `threading` to a dedicated task queue system (e.g., Celery with Redis, or Azure Functions with Azure Queues/Blob Triggers) for better scalability, fault tolerance, and management of background tasks, especially for very large files or high concurrency.
* **Persistent Task Status & History:** Use a database (e.g., Azure Table Storage, or re-enable SQLAlchemy models) to store task statuses and history instead of temporary status files, allowing users to retrieve past results.
* **Enhanced User Feedback:** Implement more granular progress updates from the background task to the frontend (e.g., using WebSockets or Server-Sent Events instead of just "pending" status from polling).
* **User Authentication & Authorization:** Secure the application if it's to be used by multiple users.
* **Configuration Management:** Move settings like Tebra WSDL URL, `EXPECTED_COLUMNS_CONFIG` to external configuration files.
* **Testing Suite:** Develop unit and integration tests.
* **API Documentation.**
* **Addressing Colab Script Limitations:** e.g., payment descriptions.
* **Input Template Download.**

## 13. Troubleshooting Common Issues
* **Tebra API Connection, Credential, File Upload/Validation errors:** (Similar to original README).
* **Asynchronous Processing Issues:**
    * **"/api/process" fails to return task\_id or returns 500 error immediately:** Check container logs (`stdout` from Gunicorn) for errors during initial file save or thread creation in the `process_file_route`. Ensure all imports (`threading`, `uuid`, `json`) are correct.
    * **Status stuck on "pending" or UI shows error checking status:**
        * Check container logs for errors from the `background_task_processor` thread. Any Python exception there will be logged.
        * Verify the `<task_id>.status` file is being written correctly to the `/tmp` directory (or `temp_files` locally) by the background thread.
        * Ensure the `/api/status/<task_id>` route can read this status file.
    * **Download fails after "completed" status:**
        * Verify `output_filename` in the JSON response from `/api/status` is correct and matches a file in the `/tmp` (or `temp_files`) directory in the container.
        * Check container logs for errors in the `/api/download_processed_file/<filename>` endpoint.
        * **Session Affinity (if multiple replicas):** Ensure Session Affinity is ON in Azure Container Apps Ingress settings if any part of your flow (especially if you revert to session-based downloads or add other session features) might be affected by requests hitting different instances. The current async download uses filenames/task IDs, making this less critical for the download itself but good for overall session consistency if Flask sessions are used elsewhere.
* **Browser errors after deploying `main.js` changes:** Clear browser cache thoroughly. Check browser's developer console (Network and Console tabs) for JavaScript errors or failed HTTP requests to `/api/status` or `/api/download_processed_file`.
* **Inflated/Incorrect Charge Amounts:** (Same as original README - verify `get_total_charge_amount_for_encounter_phase3` logic).

---
<p align="center">
  Developed by Saqib Sherwani
  <br>
  Copyright © 2025 • All Rights Reserved
</p>
