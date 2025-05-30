// Main JavaScript for Tebra Automation Tool

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const fileUploadArea = document.getElementById('file-upload-area');
    const fileInput = document.getElementById('file-input');
    const fileNameDisplay = document.getElementById('file-name');
    const processButton = document.getElementById('process-button');
    const downloadButton = document.getElementById('download-button');
    const resultsSection = document.getElementById('results-section');
    const resultsTable = document.getElementById('results-table');
    const resultsTableBody = document.getElementById('results-table-body');
    const alertContainer = document.getElementById('alert-container');
    const progressContainer = document.getElementById('progress-container');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const credentialsForm = document.getElementById('credentials-form');

    let currentPollingInterval = null; 

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
            updateFileNameDisplay();
        }
    });
    
    fileInput.addEventListener('change', updateFileNameDisplay);
    
    function updateFileNameDisplay() {
        if (fileInput.files.length) {
            const file = fileInput.files[0];
            fileNameDisplay.textContent = file.name;
            fileNameDisplay.classList.remove('hidden');
            checkProcessButtonState();
        } else {
            fileNameDisplay.textContent = '';
            fileNameDisplay.classList.add('hidden');
            processButton.disabled = true;
        }
    }
    
    const credentialInputs = credentialsForm.querySelectorAll('input');
    credentialInputs.forEach(input => {
        input.addEventListener('input', checkProcessButtonState);
    });
    
    function checkProcessButtonState() {
        const fileSelected = fileInput.files.length > 0;
        const credentialsComplete = Array.from(credentialInputs).every(input => input.value.trim() !== '');
        processButton.disabled = !(fileSelected && credentialsComplete);
    }
    
    processButton.addEventListener('click', function() {
        progressContainer.classList.remove('hidden');
        progressBarFill.style.width = '0%'; 
        processButton.disabled = true;
        resultsSection.classList.add('hidden');
        if(downloadButton) {
            downloadButton.classList.add('hidden');
            downloadButton.disabled = true;
        }
        clearAlerts(); 

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('customer_key', document.getElementById('customer-key').value);
        formData.append('username', document.getElementById('username').value);
        formData.append('password', document.getElementById('password').value);

        let progress = 0;
        const uploadProgressInterval = setInterval(() => {
            progress += 10;
            if (progress >= 30) { // Initial progress for "uploading/initiating"
                clearInterval(uploadProgressInterval);
            }
            progressBarFill.style.width = `${progress}%`;
        }, 100);

        fetch('/api/process', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            clearInterval(uploadProgressInterval); 
            if (!response.ok) {
                return response.json().catch(() => {
                    throw new Error(`Initial request failed: ${response.statusText} (Status: ${response.status})`);
                }).then(errData => {
                    throw new Error(errData.error || `Initial request failed: ${response.statusText} (Status: ${response.status})`);
                });
            }
            return response.json();
        })
        .then(data => {
            progressBarFill.style.width = '30%'; // Set to 30% after /api/process returns (processing starts)
            showAlert('info', data.message || "Processing started. Checking status...");
            if (data.task_id) {
                pollStatus(data.task_id);
            } else {
                throw new Error("Task ID not received from server.");
            }
        })
        .catch(error => {
            clearInterval(uploadProgressInterval);
            progressBarFill.style.width = '0%'; 
            progressContainer.classList.add('hidden');
            processButton.disabled = false;
            console.error('Error initiating processing:', error);
            showAlert('danger', error.message || 'An error occurred while initiating the process.');
        });
    });

    function pollStatus(taskId) {
        if (currentPollingInterval) {
            clearInterval(currentPollingInterval); 
        }

        let dots = 0;
        // Start polling progress from where the initial phase left off (e.g., 30%)
        let currentProgressValue = parseFloat(progressBarFill.style.width) || 30;
        const maxPollingProgress = 95; // Cap polling progress before final 100%

        currentPollingInterval = setInterval(() => {
            fetch(`/api/status/${taskId}`)
                .then(response => {
                    if (!response.ok) {
                        clearInterval(currentPollingInterval);
                        processButton.disabled = false; 
                        progressContainer.classList.add('hidden');
                         return response.json().catch(() => { // Try to parse JSON error from server
                            throw new Error(`Status check failed: ${response.statusText} (Status: ${response.status})`);
                        }).then(errData => { // If JSON error object exists, use its message
                            throw new Error(errData.error || `Status check failed: ${response.statusText} (Status: ${response.status})`);
                        });
                    }
                    return response.json();
                })
                .then(statusData => {
                    dots = (dots + 1) % 4;
                    let processingDotsText = "Processing" + ".".repeat(dots);

                    if (statusData.status === "completed") {
                        clearInterval(currentPollingInterval);
                        progressBarFill.style.width = '100%';
                        showAlert('success', statusData.message || "Processing complete! Attempting to download file.");
                        if (statusData.output_filename) {
                            triggerDownload(statusData.output_filename, statusData.original_download_name);
                        } else {
                            showAlert('warning', "Processing complete, but output filename not found for download.");
                        }
                        setTimeout(() => { 
                           progressContainer.classList.add('hidden');
                           progressBarFill.style.width = '0%'; 
                           processButton.disabled = false;
                        }, 3000);
                    } else if (statusData.status === "error") {
                        clearInterval(currentPollingInterval);
                        progressBarFill.style.width = '100%'; 
                        showAlert('danger', statusData.message || "An error occurred during background processing.");
                        setTimeout(() => {
                           progressContainer.classList.add('hidden');
                           progressBarFill.style.width = '0%'; 
                           processButton.disabled = false;
                        }, 3000);
                    } else if (statusData.status === "pending") {
                        // Increment progress slowly, but don't let it exceed maxPollingProgress
                        if (currentProgressValue < maxPollingProgress) {
                            currentProgressValue += 5; // Increment by 5% each poll interval (adjust as needed)
                            if (currentProgressValue > maxPollingProgress) {
                                currentProgressValue = maxPollingProgress;
                            }
                        }
                        progressBarFill.style.width = `${currentProgressValue}%`;
                        showAlert('info', statusData.message || processingDotsText); 
                    } else {
                        showAlert('warning', `Unknown status: ${statusData.status}. Message: ${statusData.message}`);
                        // Optionally stop polling for unknown status if it's considered an error state
                        // clearInterval(currentPollingInterval);
                        // processButton.disabled = false;
                    }
                })
                .catch(error => {
                    clearInterval(currentPollingInterval);
                    progressContainer.classList.add('hidden');
                    progressBarFill.style.width = '0%';
                    processButton.disabled = false;
                    console.error('Error polling status:', error);
                    showAlert('danger', error.message || "Error checking processing status.");
                });
        }, 5000); // Poll every 5 seconds (adjust as needed)
    }

    function triggerDownload(filenameOnServer, originalDownloadName) {
        if (!filenameOnServer) {
            showAlert('danger', 'Download cannot start: filename not provided.');
            return;
        }
        fetch(`/api/download_processed_file/${filenameOnServer}`)
            .then(response => {
                if (!response.ok) {
                    return response.text().then(text => { 
                        throw new Error(`Download failed: ${response.statusText} (Status: ${response.status}). Server: ${text}`);
                    });
                }
                return response.blob();
            })
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                
                const downloadFileName = originalDownloadName || filenameOnServer.replace(/^Processed_|_([a-f0-9\-]{36})_(\d{8}_\d{6})/i, '');

                a.download = downloadFileName;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                showAlert('success', 'File download initiated!');
                if(downloadButton) { 
                    downloadButton.disabled = false;
                    downloadButton.classList.remove('hidden');
                }
            })
            .catch(error => {
                console.error('Error downloading file:', error);
                showAlert('danger', error.message || 'An error occurred while downloading the file.');
                if(downloadButton) { 
                    downloadButton.disabled = false;
                    downloadButton.classList.remove('hidden');
                }
            });
    }
    
    const manualDownloadButton = document.getElementById('download-button');
    if (manualDownloadButton) {
        // Keep the manual download button, but it's initially hidden.
        // It becomes visible if an automatic download is triggered or if there's an error.
        manualDownloadButton.classList.add('hidden');
        manualDownloadButton.disabled = true;
        manualDownloadButton.addEventListener('click', () => {
            showAlert('info', "Manual download clicked. This will attempt to download the last processed file if available.");
            // This manual button ideally needs to know the last 'filenameOnServer' and 'originalDownloadName'
            // For simplicity, if these were stored globally after a successful 'completed' status:
            // if (window.lastProcessedFilenameOnServer && window.lastProcessedOriginalName) {
            //    triggerDownload(window.lastProcessedFilenameOnServer, window.lastProcessedOriginalName);
            // } else {
            //    showAlert('warning', 'No file information available for manual download. Please process a file first.');
            // }
            // For now, this button won't be very useful without storing the last filenames.
            // The current logic in triggerDownload (called by pollStatus) is better.
        });
    }

    function clearAlerts() {
        alertContainer.innerHTML = '';
    }

    function showAlert(type, message) {
        clearAlerts(); 
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type}`;
        alertDiv.textContent = message;
        alertContainer.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 7000); 
    }

    if (resultsSection && resultsTable) { 
        resultsTable.classList.add('hidden'); 
    }
});
