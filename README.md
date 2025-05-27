# Tebra Automation Tool - Flask Web Application

## 1. Project Overview

**Name:** Tebra Automation Tool
**Purpose:** This Flask web application automates various tasks within the Tebra Practice Management System (PMS) by interacting with the Tebra SOAP API. It aims to streamline workflows related to patient data, payments, and charge entry.
**Origin:** The application is an enhanced web-based version of an original Python script (`tebra_automation_tool_v2.py`) designed for Google Colab.

**Core Functionalities:**
* **Patient and Insurance Verification (Phase 1):**
    * Upload an Excel file containing patient and service information.
    * For each relevant row, the application fetches patient details (Name, DOB) and primary active insurance information (Insurance Name, Insurance ID, Insurance Status) from Tebra using Patient ID and Date of Service (DOS).
* **Payment Posting (Phase 2):**
    * If payment details (Batch #, Payment Amount, Source, Reference Number) are provided in the input Excel, the application posts these payments to Tebra for the respective patients.
* **Encounter Creation & Charge Entry (Phase 3):**
    * Rows with the same Patient ID, DOS, and Practice are grouped to create a single encounter in Tebra.
    * Creates encounters with details like Rendering Provider, Scheduling Provider, Referring Provider (if found), Encounter Mode, Place of Service (POS), hospitalization dates, and multiple service lines (Procedures, Modifiers, Units, Diagnoses).
* **Results & Output:**
    * After processing, the application updates the input data with fetched information (Patient Name, DOB, Insurance details, Encounter ID, Charge Status, Charge Amount) and any processing errors for each row.
    * Provides a summary of processing (total rows, encounters created, payments posted, failed rows).
    * Allows the user to download the processed data as an Excel file.

## 2. Technology Stack

* **Backend:** Python 3.x, Flask
* **Frontend:** HTML5, CSS3, JavaScript (ES6)
* **Python Libraries:**
    * `Flask`: Web framework.
    * `pandas`: Data manipulation, Excel file reading/writing.
    * `zeep`: SOAP client for Tebra API interaction.
    * `openpyxl`: Used by pandas for reading/writing `.xlsx` files.
    * `pytz`: For timezone handling (though direct usage might be minimal, it's a common dependency with datetime operations).
    * `requests`: HTTP library, underlying dependency for `zeep`.
    * `Flask-SQLAlchemy`: ORM for database interaction (currently commented out in `main.py` but present as a dependency).
    * `gunicorn`: WSGI HTTP Server for production deployment.
* **External API:** Tebra SOAP Web Services (WSDL URL: `https://webservice.kareo.com/services/soap/2.1/KareoServices.svc?singleWsdl`)

## 3. Project Structure
TebraAuto/
├── main.py                     # Flask app entry point, app initialization
├── requirements.txt            # Python dependencies
├── static/                     # Frontend assets
│   ├── css/
│   │   └── styles.css          # Main stylesheet
│   ├── img/
│   │   └── owl-logo.png        # Logo image (referenced in index.html)
│   ├── js/
│   │   └── main.js             # Frontend JavaScript logic
│   └── index.html              # Main HTML page for the UI
├── src/                        # Source code directory
│   ├── init.py             # Makes 'src' a Python package
│   ├── models/
│   │   ├── init.py
│   │   └── user.py             # SQLAlchemy database models (currently minimal)
│   └── routes/
│       ├── init.py
│       └── user.py             # Defines API endpoints and core backend logic
└── temp_files/                 # (Created by user.py) Stores processed Excel files temporarily

* **`main.py`**: Initializes the Flask application, registers blueprints, and sets up routes for serving static files and the main `index.html`. Database initialization is present but commented out.
* **`src/routes/user.py`**: This is the core of the backend. It handles:
    * API endpoints: `/api/process` (for file upload and processing) and `/api/download` (for downloading results).
    * Interaction with the Tebra SOAP API via the `zeep` library.
    * Validation of uploaded Excel files.
    * The main multi-phase processing logic for patient data, payments, and encounters.
    * Caching of Tebra entity IDs to optimize API calls.
* **`src/models/user.py`**: Defines a SQLAlchemy `db` instance. Currently, no specific models are implemented for this application's core logic beyond this initialization.
* **`static/`**: Contains all frontend files.
    * `index.html`: The single-page user interface for interacting with the application. Includes forms for credentials, file upload, and displaying results.
    * `css/styles.css`: Provides the visual styling for `index.html`.
    * `js/main.js`: Handles client-side logic: DOM manipulation, form validation, enabling/disabling buttons, AJAX calls to the backend APIs (`/api/process`, `/api/download`), displaying progress, and rendering results.
* **`temp_files/`**: This directory is created by `src/routes/user.py` if it doesn't exist. It's used to temporarily store the processed Excel files before they are downloaded by the user.

## 4. Setup and Installation

**Prerequisites:**
* Python (3.7 or higher recommended)
* `pip` (Python package installer)

**Installation Steps:**
1.  **Clone the Repository (Example):**
    ```bash
    git clone <repository-url>
    cd TebraAuto
    ```
    (Assuming the project root is `TebraAuto`)
2.  **Create and Activate a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```
3.  **Install Dependencies:**
    Navigate to the project root directory (where `requirements.txt` is located) and run:
    ```bash
    pip install -r requirements.txt
    ```
   
4.  **Environment Variables:**
    Currently, the core application logic does not strictly require environment variables unless the database functionality (commented out in `main.py`) is enabled. If enabling the database, ensure variables like `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` are set.

## 5. Running the Application

1.  **Development Mode:**
    From the project root directory, run:
    ```bash
    python main.py
    ```
    The application will typically be accessible at `http://127.0.0.1:5000` or `http://localhost:5000`.

2.  **Production Mode (using Gunicorn):**
    Gunicorn is listed in `requirements.txt`. An example command to run with Gunicorn:
    ```bash
    gunicorn --workers 4 --bind 0.0.0.0:5000 main:app
    ```
    (Adjust workers and binding as needed for your environment).

## 6. Application Workflow

The application operates as a single-page web tool.

**A. Frontend (`static/index.html`, `static/js/main.js`):**
1.  **Credentials Input:** The user enters their Tebra Customer Key, Username (email), and Password into the designated form fields.
2.  **File Upload:**
    * The user uploads an Excel file (`.xlsx` or `.xls`) using the drag-and-drop area or the browse button.
    * The file must contain a sheet named "Charges".
    * The filename is displayed.
3.  **Process Initiation:** The "Process Charges" button is enabled only when all credential fields are filled and a file has been selected.
4.  **API Call to Backend:**
    * When "Process Charges" is clicked, `main.js` constructs `FormData` containing the uploaded file and the credential values.
    * An asynchronous POST request is made to the `/api/process` endpoint.
5.  **Progress & Results Display:**
    * A progress bar is shown (currently simulated on the frontend, with actual progress happening on the backend).
    * Upon receiving a response from `/api/process`:
        * Success: A success alert is shown with summary statistics. The results table is populated with row-by-row details from the backend's JSON response. The "Download Output Excel" button is enabled.
        * Error: An error alert is shown.
6.  **Download Output:**
    * Clicking the "Download Output Excel" button triggers a GET request to `/api/download`.
    * The browser handles the file download. The filename includes the current date (e.g., `Processed_Tebra_Data_YYYY-MM-DD.xlsx`).

**B. Backend (`src/routes/user.py`):**

* **`/api/process` Endpoint (POST):**
    1.  **Request Handling:** Receives the `file`, `customer_key`, `username`, and `password` from the form data.
    2.  **Credential Preparation:** Escapes special XML characters in the password using `escape_xml_special_chars`.
    3.  **Tebra API Client Setup:**
        * Initializes the `zeep` client with the Tebra WSDL URL (`create_api_client_adapted`).
        * Builds the Tebra request header (`build_request_header_adapted`).
    4.  **File Validation (`validate_spreadsheet_adapted`):**
        * Reads the uploaded file stream into a pandas DataFrame.
        * Specifically looks for and processes the "Charges" sheet.
        * Normalizes column headers (lowercase, trimmed spaces).
        * Validates against `EXPECTED_COLUMNS_CONFIG` to ensure all critical input columns are present and maps logical column names to actual headers found in the file.
        * Adds any missing expected output columns to the DataFrame.
        * Returns the DataFrame, column map, and any validation errors.
    5.  **Core Processing Logic (`run_all_phases_processing_adapted`):**
        * Takes the validated DataFrame, column map, Tebra client, and header as input.
        * Initializes local Python dictionary caches for Tebra entity IDs (practice, service location, provider types, case ID) to minimize redundant API calls during the request.
        * Adds an `original_excel_row_num` column for better referencing.
        * Initializes/clears output columns in the DataFrame.
        * **Row-wise Processing (Phases 1 & 2):**
            * Iterates through each row of the DataFrame.
            * **Phase 1 (Patient/Insurance Data):**
                * Calls `phase1_fetch_patient_and_insurance` with Patient ID, Practice Name (from Excel), and DOS.
                * This function calls Tebra's `GetPatient` API.
                * It extracts Patient Name, DOB, and details of the primary, active insurance policy (Plan Name, Policy Number, Status) effective on the DOS.
                * Updates the current row in the DataFrame with these fetched details and any errors.
            * **Phase 2 (Payment Posting):**
                * If payment-related columns (PP Batch #, Patient Payment, Patient Payment Source) are present and valid in the row:
                    * Resolves Practice Name to Tebra Practice ID using `get_practice_id_by_name` (utilizes cache).
                    * Calls `phase2_post_tebra_payment` with necessary details (Patient ID, Practice ID, batch, amount, source, reference number).
                    * This function calls Tebra's `CreatePayment` API.
                    * Updates the DataFrame row with payment status (e.g., "Payment #12345 Posted." or error messages).
        * **Grouped Processing (Phase 3 - Encounter Creation):**
            * Filters the DataFrame for rows suitable for encounter creation (valid Patient ID, DOS, Practice Name from Excel, and fetched Patient Name from Phase 1).
            * Groups these rows by Patient ID, DOS, and Practice Name (from Excel) to create one encounter per group.
            * For each group:
                * Calls `_create_encounter_for_group_and_get_details`.
                * **Inside `_create_encounter_for_group_and_get_details`:**
                    * Resolves Practice Name (from Excel, which acts as Service Location context here) to Tebra Service Location ID using `get_service_location_id_by_name` (with Tebra Practice ID context, uses cache).
                    * Fetches Tebra Patient Case ID using `get_case_id_for_patient_phase3` (uses cache).
                    * Resolves Rendering Provider name to Tebra Provider ID using `get_provider_id_by_name_phase3` (uses cache).
                    * Handles optional Referring Provider: Looks up details (NPI, Tebra ID) using `get_referring_provider_details_for_encounter` and prepares payload.
                    * Handles optional Scheduling Provider similarly.
                    * Determines Place of Service (POS) code and name using `create_place_of_service_payload_phase3` based on Excel POS and Encounter Mode.
                    * Prepares hospitalization data (Admit/Discharge dates) if provided.
                    * Constructs service line payloads for each row in the group using `create_service_line_payload_phase3` (Procedures, Modifiers, Units, Diagnoses). Collects a list of unique procedure codes for this encounter.
                    * Builds the complete `EncounterCreate` payload for Tebra.
                    * Calls Tebra's `CreateEncounter` API.
                    * If encounter creation is successful (returns an Encounter ID > 0):
                        * Calls `get_encounter_details_phase3` to fetch the `EncounterStatus` (e.g., Draft, Billed).
                        * Calls `get_total_charge_amount_for_encounter_phase3` (passing the created Encounter ID, Patient ID, Practice Name, DOS, and the list of procedure codes for this encounter) to get the total charge amount. This function now makes a single API call using one procedure code and then sums relevant lines.
                    * Updates all DataFrame rows corresponding to this group with the created Encounter ID, Charge Status, Charge Amount, and any processing messages/errors.
    6.  **Output File Generation:**
        * After all processing, the modified DataFrame is saved to a new Excel file (e.g., `Processed_Tebra_Data_YYYYMMDD_HHMMSS.xlsx`) in the `temp_files/` directory. The `original_excel_row_num` column is dropped before saving.
    7.  **Session Management:** The path to the processed file and a user-friendly download name are stored in the Flask session.
    8.  **Response to Frontend:** Returns a JSON response containing summary statistics (`total_rows`, `encounters_created`, `payments_posted`, `failed_rows`) and a list of `results` (one entry per original Excel row with its original row number, practice name, patient ID, and a consolidated status/error message).
    9.  **Error Handling:** Catches `zeep.exceptions.Fault` (SOAP errors) and other general exceptions, returning appropriate JSON error messages to the frontend.

* **`/api/download` Endpoint (GET):**
    1.  Retrieves the `processed_file_path` and `processed_file_download_name` from the session.
    2.  If the file exists, it uses `send_file` to send the processed Excel file to the user's browser for download.
    3.  Handles potential errors if the file is not found.

## 7. Key Functions and Logic in `src/routes/user.py`

* **API Interaction:**
    * `TEBRA_WSDL_URL`: Constant defining the Tebra SOAP API endpoint.
    * `escape_xml_special_chars()`: Sanitizes passwords for XML/SOAP.
    * `create_api_client_adapted()`: Creates the `zeep` SOAP client.
    * `build_request_header_adapted()`: Constructs the `RequestHeader` for Tebra API calls.
* **File Validation & Preparation:**
    * `UPLOAD_FOLDER = 'temp_files'`: Defines where processed files are stored.
    * `EXPECTED_COLUMNS_CONFIG`: A crucial dictionary that defines:
        * Logical names for all columns the application interacts with.
        * `"normalized"`: The lowercase, space-normalized version of the header expected in the Excel file.
        * `"is_critical_input"`: Boolean indicating if the column is mandatory for core operations.
        * `"purpose"`: A description of the column's role.
       
    * `normalize_header_name_adapted()`: Standardizes column headers from the Excel file for comparison.
    * `validate_spreadsheet_adapted()`: Core validation logic for the input Excel.
* **Tebra Entity ID Fetching (with caching):**
    * `get_practice_id_by_name()`: Fetches Tebra Practice ID.
    * `get_service_location_id_by_name()`: Fetches Tebra Service Location ID based on name and Tebra Practice ID.
    * `get_provider_id_by_name_phase3()`: Fetches Tebra Provider ID for Rendering/Scheduling providers (uses flexible name matching).
    * `get_referring_provider_details_for_encounter()`: Fetches details (ID, NPI, Name) for Referring Providers, prioritizing those explicitly typed as "Referring Provider" in Tebra.
    * `get_case_id_for_patient_phase3()`: Fetches the primary Tebra Patient Case ID.
* **Core Logic Functions:**
    * `phase1_fetch_patient_and_insurance()`: Handles fetching patient demographics and insurance.
    * `phase2_post_tebra_payment()`: Handles posting patient payments.
    * `_create_encounter_for_group_and_get_details()`: Orchestrates the creation of a single encounter for a group of service lines.
    * `create_place_of_service_payload_phase3()`: Determines and creates the POS payload.
    * `create_service_line_payload_phase3()`: Creates payload for individual service lines within an encounter.
    * `get_encounter_details_phase3()`: Fetches status of a newly created encounter.
    * `get_total_charge_amount_for_encounter_phase3()`: Calculates total charges for an encounter (recently corrected to avoid over-summing).
    * `parse_tebra_xml_error_phase3()`: Simplifies complex XML error messages from Tebra for display.
    * `run_all_phases_processing_adapted()`: The main orchestrator function that drives the entire data processing workflow after file validation.
* **Helper/Utility:**
    * `display_message()`: Prints formatted log messages to the server console.
    * `is_date_value_present()`: Checks validity of date strings.
    * `PAYMENT_SOURCE_TO_CODE`: Maps payment source strings to Tebra codes.
    * `format_datetime_for_api_phase3()`: Formats dates for Tebra API.

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

**Output Columns (populated by the application):**
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

* **Backend Logging:** The `display_message(level, message)` function in `src/routes/user.py` prints logs to the server console, prefixed with levels like `[INFO]`, `[ERROR]`, `[DEBUG]`, `[WARNING]`. This is useful for server-side troubleshooting.
* **Frontend Alerts:** `main.js` uses Bootstrap-style alerts to show success or error messages to the user in the UI (e.g., "Successfully processed X rows.", "An error occurred...").
* **API Error Responses:** Backend API endpoints (`/api/process`, `/api/download`) return JSON responses. In case of errors, these include an `"error"` key with a descriptive message (e.g., `{"error": "No file part"}`).
* **Output Excel "Error" Column:** The processed Excel file includes an "Error" column. This column provides row-specific feedback, including successful operations (like payment posting confirmation, encounter creation ID) and any errors encountered during that row's processing stages (Phase 1, 2, or 3).
* **SOAP Faults:** `zeep.exceptions.Fault` are caught specifically in the backend to handle Tebra API errors. Detailed SOAP errors might be logged to the console.

## 10. Caching Mechanism

To optimize performance and reduce the number of redundant calls to the Tebra API, the application implements an in-memory caching strategy within the `run_all_phases_processing_adapted` function in `src/routes/user.py`.

* **Scope:** Caches are initialized locally for each individual `/api/process` request. This means they are not shared across different user requests or sessions but are effective for a single bulk processing job.
* **Cached Entities:**
    * Tebra Practice IDs (mapped from Practice Names).
    * Tebra Service Location IDs (mapped from Service Location Names, contextualized by Tebra Practice ID).
    * Tebra Provider IDs for Rendering, Scheduling providers (mapped from names, contextualized by Tebra Practice ID).
    * Tebra Referring Provider details (mapped from names, contextualized by Tebra Practice ID).
    * Tebra Patient Case IDs (mapped from Tebra Patient IDs).
* **Implementation:** Python dictionaries are used (e.g., `g_practice_id_cache_local`, `g_service_location_id_cache_local`, etc.). Before making an API call to fetch these IDs, the respective helper functions first check if the ID is already in the cache for the current processing run. If found, the cached ID is used; otherwise, an API call is made, and the result is stored in the cache for subsequent use within the same run.

## 11. Evolution from Colab Script (`tebra_automation_tool_v2.py`)

This Flask application is a significant refactoring and enhancement of the original Colab Python script (`tebra_automation_tool_v2.py`).
* **Web Interface:** Provides a user-friendly web UI instead of requiring code execution in a Colab notebook.
* **API-based Architecture:** Separates frontend and backend logic.
* **Robust Error Handling:** Improved error feedback to the user and more structured backend error management.
* **Corrections & Enhancements:**
    * The logic for fetching patient insurance details (Phase 1) has been aligned to correctly update the output.
    * The calculation of total service charge amounts for encounters (Phase 3) has been corrected to prevent inflated sums when encounters have multiple service lines.
    * Functionality such as fetching Referring Provider NPIs for encounter creation is incorporated.
* **Deployment Ready:** Includes `gunicorn` for easier deployment.

## 12. Potential Future Enhancements / Areas for Development

* **Enhanced User Feedback:** More granular progress updates from the backend to the frontend (e.g., using WebSockets or Server-Sent Events instead of simulated progress).
* **Persistent Job History:** Implement database integration (currently commented out) to store a history of uploads, processing status, and links to output files.
* **User Authentication & Authorization:** Secure the application if it's to be used by multiple users.
* **Configuration Management:** Move settings like Tebra WSDL URL, `EXPECTED_COLUMNS_CONFIG`, or `POS_CODE_MAP_PHASE3` to external configuration files.
* **Testing Suite:** Develop unit tests for backend logic (especially API interaction and data transformation) and integration tests for API endpoints.
* **API Documentation:** Generate API documentation (e.g., using Swagger/OpenAPI) if other services need to interact with the backend.
* **Addressing Colab Script Limitations:**
    * Implement functionality to enter descriptions during payment posting (e.g., SharePoint document name), if feasible via the Tebra API.
* **Asynchronous Task Processing:** For very large files, consider using a task queue (e.g., Celery with Redis/RabbitMQ) to handle processing asynchronously, preventing HTTP timeouts and allowing users to leave the page.
* **Input Template Download:** Provide a downloadable Excel template for users.

## 13. Troubleshooting Common Issues

* **Tebra API Connection Errors:**
    * Verify the `TEBRA_WSDL_URL` in `src/routes/user.py` is correct and accessible.
    * Check your server's internet connectivity.
    * Ensure the Tebra SOAP service is operational.
    * Look for `zeep` or `requests` related errors in the server console.
* **Credential Errors:**
    * "API Auth Error" usually means the Tebra Customer Key, Username, or Password are incorrect. Double-check them.
    * The application attempts to escape special characters in passwords, but highly unusual passwords might still pose issues.
* **File Upload/Validation Errors:**
    * "No file part" or "No selected file": Ensure a file is actually being sent from the frontend.
    * "Unsupported file type": The app only accepts `.xlsx` and `.xls` files.
    * "Target sheet 'Charges' not found": The Excel file MUST contain a sheet explicitly named "Charges".
    * "CRITICAL INPUT COLUMNS ARE MISSING...": One or more mandatory column headers (as defined by the "normalized" names in `EXPECTED_COLUMNS_CONFIG`) are not found in the "Charges" sheet. Compare file headers with the configuration.
* **Data Processing Errors (in Output Excel "Error" column or server logs):**
    * "Patient ID missing", "Practice Name missing": Critical data missing in a row.
    * "API Error (GetPt)", "API Error (CreatePayment)", "Enc API Err": Errors directly from the Tebra API. The `parse_tebra_xml_error_phase3` function tries to simplify these. Check server logs for more details if the simplified message is unclear.
    * "SL '[PracticeName]' not found", "Provider ID for '[Name]' not found", "Case ID not found": The application could not find the specified entity in Tebra based on the provided name/ID. Verify the data in the Excel sheet matches the data in Tebra exactly.
    * "Invalid DOS", "Invalid Payment amount": Data format issues in the Excel file.
    * "Charge Fetch Error": Issues during the `get_total_charge_amount_for_encounter_phase3` step.
* **Download Issues:**
    * "Processed file not found...": This might happen if the processing failed before a file was saved, or if there's an issue with session management or file system permissions for the `temp_files/` directory.
* **Inflated/Incorrect Charge Amounts:** This was a known issue due to over-summing when an encounter had multiple service lines. The `get_total_charge_amount_for_encounter_phase3` function has been corrected to address this by making a single API call using a representative procedure code and then carefully summing the charges for the specific encounter. Ensure this corrected version is in place.

---
*Developed by Saqib Sherwani (as per footer in `index.html`) and maintained/modified by AI/developers.*
