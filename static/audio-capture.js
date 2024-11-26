
class AudioRecorder {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.ws = null;
        this.isRecording = false;
    }

    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            // Connect to WebSocket on localhost
            this.ws = new WebSocket('ws://localhost:8000/ws');

            this.ws.onopen = () => {
                console.log('WebSocket connection established');

                // Create MediaRecorder after WebSocket is connected
                this.mediaRecorder = new MediaRecorder(stream, {
                    mimeType: "audio/webm;codecs=opus" // Explicitly specify MIME type
                });

                this.mediaRecorder.ondataavailable = async (event) => {
                    if (event.data.size > 0) {
                        console.log(`Captured audio chunk of size: ${event.data.size} bytes`);

                        // Convert Blob to ArrayBuffer
                        const arrayBuffer = await event.data.arrayBuffer();
                        
                        // Send audio chunk to server via WebSocket
                        if (this.ws.readyState === WebSocket.OPEN) {
                            console.log('Sending audio chunk to server...');
                            this.ws.send(arrayBuffer);
                        }
                    }
                };

                // Start recording
                this.mediaRecorder.start(1000); // Capture in 1-second chunks
                this.isRecording = true;
                console.log('Recording started');
            };

            async function typeTranscription(textArea, text, index = 0) {
                if (index < text.length) {
                    textArea.value += text.charAt(index);
                    setTimeout(() => typeTranscription(textArea, text, index + 1), 10); // Delay between characters
                }
            }
            this.ws.onmessage = (event) => {
                console.log('Received transcription:', event.data);

                // Dynamically fetch the textarea each time a message is received
                const transcriptionArea = document.getElementById('transcription');
                console.log(transcriptionArea);
                if (transcriptionArea) {
                    // Use the globally exposed typeTranscription function
                    typeTranscription(transcriptionArea, event.data + "\n"); // Adding newline for readability
                }
            };
            
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

            this.ws.onclose = () => {
                console.log('WebSocket connection closed');
                this.stopRecording();
            };

        } catch (error) {
            console.error('Error starting recording:', error);
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;

            // Close WebSocket connection
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.close();
            }

            // Stop all audio tracks
            this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            console.log('Recording stopped');
        }
    }
}

// Initialize recorder
const audioRecorder = new AudioRecorder();

// Export functions for buttons
window.startRecording = () => audioRecorder.startRecording();
window.stopRecording = () => audioRecorder.stopRecording();
