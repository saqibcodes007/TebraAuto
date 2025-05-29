// Main JavaScript for Tebra Automation Tool

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const fileUploadArea = document.getElementById('file-upload-area');
    const fileInput = document.getElementById('file-input');
    const fileName = document.getElementById('file-name');
    const processButton = document.getElementById('process-button');
    const downloadButton = document.getElementById('download-button');
    const resultsSection = document.getElementById('results-section');
    const resultsTable = document.getElementById('results-table'); // Keep for potential future use or hiding
    const resultsTableBody = document.getElementById('results-table-body');
    const alertContainer = document.getElementById('alert-container');
    const progressContainer = document.getElementById('progress-container');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const credentialsForm = document.getElementById('credentials-form');
    
    // File Upload Handling
    fileUploadArea.addEventListener('click', () => {
        fileInput.click();
    });
    
    fileUploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        fileUploadArea.classList.add('highlight');
    });
    
    fileUploadArea.addEventListener('dragleave', () => {
        fileUploadArea.classList.remove('highlight');
    });
    
    fileUploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        fileUploadArea.classList.remove('highlight');
        
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            updateFileName();
        }
    });
    
    fileInput.addEventListener('change', updateFileName);
    
    function updateFileName() {
        if (fileInput.files.length) {
            const file = fileInput.files[0];
            fileName.textContent = file.name;
            fileName.classList.remove('hidden');
            
            // Only enable process button if credentials are also filled
            checkProcessButtonState();
        } else {
            fileName.textContent = '';
            fileName.classList.add('hidden');
            processButton.disabled = true;
        }
    }
    
    // Credentials Form Handling
    const credentialInputs = credentialsForm.querySelectorAll('input');
    credentialInputs.forEach(input => {
        input.addEventListener('input', checkProcessButtonState);
    });
    
    function checkProcessButtonState() {
        const fileSelected = fileInput.files.length > 0;
        const credentialsComplete = Array.from(credentialInputs).every(input => input.value.trim() !== '');
        
        processButton.disabled = !(fileSelected && credentialsComplete);
    }
    
    // Process Button Click Handler
    processButton.addEventListener('click', function() {
        // Show progress and disable button
        progressContainer.classList.remove('hidden');
        processButton.disabled = true;
        // Hide results section and download button initially for new processing
        resultsSection.classList.add('hidden');
        downloadButton.classList.add('hidden');
        downloadButton.disabled = true;
        
        // Create form data
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('customer_key', document.getElementById('customer-key').value);
        formData.append('username', document.getElementById('username').value);
        formData.append('password', document.getElementById('password').value);
        
        // Simulate progress (will be replaced with actual progress from backend)
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
            if (progress > 90) clearInterval(progressInterval); // Stop at 90 to show completion from backend
            progressBarFill.style.width = `${progress}%`;
        }, 300);
        
        // Send data to backend
        fetch('/api/process', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            clearInterval(progressInterval);
            
            if (!response.ok) {
                // Try to parse error response as JSON, otherwise use status text
                return response.json().catch(() => {
                    throw new Error(`Network response was not ok: ${response.statusText} (Status: ${response.status})`);
                }).then(errData => {
                    // If backend sends a JSON error object like {"error": "message"}
                    throw new Error(errData.error || `Network response was not ok: ${response.statusText} (Status: ${response.status})`);
                });
            }
            return response.json();
        })
        .then(data => {
            // Complete progress bar
            progressBarFill.style.width = '100%';
            
            // Display a message in the results section instead of a table
            displayResultsMessage(data.message); // Use the message from minimal_summary
            
            // Show success message (or the message from the backend if more specific)
            if (data.message) {
                 showAlert('success', data.message);
            } else {
                // Fallback if data.message is not present, using other fields
                showAlert('success', `Successfully processed ${data.total_rows} rows. Created ${data.encounters_created} encounters. Posted ${data.payments_posted} payments. ${data.failed_rows} rows failed.`);
            }
            
            // Enable download button if download_ready is true (or if backend sends any success)
            if (data.download_ready || (data.total_rows !== undefined)) { // Check if download_ready or if it's old format with total_rows
                downloadButton.disabled = false;
                downloadButton.classList.remove('hidden');
            } else {
                downloadButton.disabled = true;
                downloadButton.classList.add('hidden');
            }
            
            // Reset process button after a short delay
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                progressBarFill.style.width = '0%';
                processButton.disabled = false; 
            }, 1000);
        })
        .catch(error => {
            clearInterval(progressInterval); // Ensure interval is cleared on error too
            progressBarFill.style.width = '100%'; // Show full progress bar even on error, then hide
            
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                progressBarFill.style.width = '0%';
            }, 1000);
            
            processButton.disabled = false; // Re-enable process button
            
            console.error('Error:', error);
            showAlert('danger', error.message || 'An error occurred while processing the file. Please try again.');
        });
    });
    
    // Download Button Click Handler
    downloadButton.addEventListener('click', function() {
        fetch('/api/download')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok during download.');
                }
                return response.blob();
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                
                const date = new Date();
                const dateString = date.toISOString().split('T')[0];
                
                a.download = `Processed_Tebra_Data_${dateString}.xlsx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a); // Clean up the link
            })
            .catch(error => {
                console.error('Error downloading file:', error);
                showAlert('danger', 'An error occurred while downloading the file. Please try again.');
            });
    });
    
    // Modified displayResults to show a message instead of a table
    function displayResultsMessage(message) {
        resultsSection.classList.remove('hidden');
        resultsTableBody.innerHTML = ''; // Clear any old table content

        // If you want to hide the table structure itself and just show a message in the section
        if (resultsTable) {
            resultsTable.classList.add('hidden'); // Hide the actual table
        }

        // Create a paragraph for the message if one doesn't exist, or update existing one
        let messageElement = document.getElementById('results-message-area');
        if (!messageElement) {
            messageElement = document.createElement('p');
            messageElement.id = 'results-message-area';
            messageElement.style.textAlign = 'center';
            messageElement.style.padding = '20px';
            // Insert it before the table if table exists, or just append to section
            if (resultsTable && resultsTable.parentNode === resultsSection) {
                 resultsSection.insertBefore(messageElement, resultsTable);
            } else {
                 resultsSection.appendChild(messageElement);
            }
        }
        
        messageElement.textContent = message || "Processing complete. Download the Excel file for detailed results.";
        
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    // Alert Display
    function showAlert(type, message) {
        const alertDiv = document.createElement('div'); // Renamed to avoid conflict
        alertDiv.className = `alert alert-${type}`;
        alertDiv.textContent = message;
        
        alertContainer.innerHTML = ''; // Clear previous alerts
        alertContainer.appendChild(alertDiv);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
});
