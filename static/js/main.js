// Main JavaScript for Tebra Automation Tool

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const fileUploadArea = document.getElementById('file-upload-area');
    const fileInput = document.getElementById('file-input');
    const fileName = document.getElementById('file-name');
    const processButton = document.getElementById('process-button');
    const downloadButton = document.getElementById('download-button');
    const resultsSection = document.getElementById('results-section');
    const resultsTable = document.getElementById('results-table');
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
            if (progress > 90) clearInterval(progressInterval);
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
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            // Complete progress bar
            progressBarFill.style.width = '100%';
            
            // Display results
            displayResults(data);
            
            // Show success message
            showAlert('success', `Successfully processed ${data.total_rows} rows. Created ${data.encounters_created} encounters. Posted ${data.payments_posted} payments. ${data.failed_rows} rows failed.`);
            
            // Enable download button
            downloadButton.disabled = false;
            downloadButton.classList.remove('hidden');
            
            // Reset process button
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                progressBarFill.style.width = '0%';
                processButton.disabled = false;
            }, 1000);
        })
        .catch(error => {
            clearInterval(progressInterval);
            progressContainer.classList.add('hidden');
            processButton.disabled = false;
            
            console.error('Error:', error);
            showAlert('danger', 'An error occurred while processing the file. Please try again.');
        });
    });
    
    // Download Button Click Handler
    downloadButton.addEventListener('click', function() {
        fetch('/api/download')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.blob();
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                
                // Get current date for filename
                const date = new Date();
                const dateString = date.toISOString().split('T')[0];
                
                a.download = `Processed_Tebra_Data_${dateString}.xlsx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
            })
            .catch(error => {
                console.error('Error:', error);
                showAlert('danger', 'An error occurred while downloading the file. Please try again.');
            });
    });
    
    // Display Results in Table
    function displayResults(data) {
        resultsSection.classList.remove('hidden');
        resultsTableBody.innerHTML = '';
        
        data.results.forEach(row => {
            const tr = document.createElement('tr');
            
            // Excel Row Number
            const tdRowNum = document.createElement('td');
            tdRowNum.textContent = row.row_number;
            tr.appendChild(tdRowNum);
            
            // Practice Name
            const tdPractice = document.createElement('td');
            tdPractice.textContent = row.practice_name;
            tr.appendChild(tdPractice);
            
            // Patient ID
            const tdPatientId = document.createElement('td');
            tdPatientId.textContent = row.patient_id;
            tr.appendChild(tdPatientId);
            
            // Results
            const tdResults = document.createElement('td');
            tdResults.textContent = row.results;
            
            // Add appropriate status class
            if (row.results.includes('Error') || row.results.includes('Failed')) {
                tdResults.classList.add('status-error');
            } else if (row.results.includes('Warning')) {
                tdResults.classList.add('status-warning');
            } else {
                tdResults.classList.add('status-success');
            }
            
            tr.appendChild(tdResults);
            
            resultsTableBody.appendChild(tr);
        });
        
        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    // Alert Display
    function showAlert(type, message) {
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.textContent = message;
        
        alertContainer.innerHTML = '';
        alertContainer.appendChild(alert);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }
});
