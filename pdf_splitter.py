import tkinter as tk
from tkinter import filedialog, messagebox
import fitz
from PIL import Image
import numpy as np
import os

def is_color_page(page, threshold=0.01):
    """
    Check if a PDF page contains colors.

    Args:
        page: fitz.Page object
        threshold: Minimum percentage of color pixels to consider page as colored

    Returns:
        bool: True if page is colored, False if black and white
    """
    # Render page to pixmap
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Lower resolution for faster processing
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # Convert to numpy array
    img_array = np.array(img)

    # Calculate difference between RGB channels
    # If all channels are nearly equal, it's grayscale
    diff = np.abs(img_array[:,:,0].astype(float) - img_array[:,:,1].astype(float)) + \
           np.abs(img_array[:,:,1].astype(float) - img_array[:,:,2].astype(float)) + \
           np.abs(img_array[:,:,2].astype(float) - img_array[:,:,0].astype(float))

    # Count pixels that have significant color difference
    color_pixels = np.sum(diff > 30)  # Threshold for color detection
    total_pixels = img_array.shape[0] * img_array.shape[1]

    # Calculate percentage of colored pixels
    color_percentage = color_pixels / total_pixels

    return color_percentage > threshold

def split_pdf_by_colors(input_pdf_path, output_colored_path, output_bw_path):
    """
    Split a PDF into two files: one with colored pages and one with black & white pages.

    Args:
        input_pdf_path: Path to input PDF file
        output_colored_path: Path for output PDF with colored pages
        output_bw_path: Path for output PDF with black & white pages
    """
    try:
        # Open the input PDF
        doc = fitz.open(input_pdf_path)

        # Create new PDF documents
        colored_doc = fitz.open()
        bw_doc = fitz.open()

        # Track page indices for maintaining order
        colored_pages = []
        bw_pages = []

        # Process each page
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)

            if is_color_page(page):
                # Insert colored page into colored document
                colored_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                colored_pages.append(page_num + 1)
            else:
                # Insert black & white page into BW document
                bw_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                bw_pages.append(page_num + 1)

        # Save the documents
        if len(colored_doc) > 0:
            colored_doc.save(output_colored_path)

        if len(bw_doc) > 0:
            bw_doc.save(output_bw_path)

        # Close documents
        colored_doc.close()
        bw_doc.close()
        doc.close()

        return colored_pages, bw_pages

    except Exception as e:
        raise Exception(f"Error splitting PDF: {str(e)}")

class PDFSplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Color Splitter")
        self.root.geometry("600x400")

        # Variables
        self.input_pdf_path = tk.StringVar()
        self.output_dir = tk.StringVar()

        self.create_widgets()

    def create_widgets(self):
        # Main frame
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = tk.Label(main_frame, text="PDF Color Splitter", font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))

        # Input PDF selection
        input_frame = tk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=5)

        tk.Label(input_frame, text="Input PDF:", font=("Arial", 10)).pack(anchor=tk.W)

        input_row = tk.Frame(input_frame)
        input_row.pack(fill=tk.X, pady=5)

        self.input_entry = tk.Entry(input_row, textvariable=self.input_pdf_path, width=50)
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_btn = tk.Button(input_row, text="Browse", command=self.browse_input_pdf)
        browse_btn.pack(side=tk.RIGHT)

        # Output directory selection
        output_frame = tk.Frame(main_frame)
        output_frame.pack(fill=tk.X, pady=5)

        tk.Label(output_frame, text="Output Directory:", font=("Arial", 10)).pack(anchor=tk.W)

        output_row = tk.Frame(output_frame)
        output_row.pack(fill=tk.X, pady=5)

        self.output_entry = tk.Entry(output_row, textvariable=self.output_dir, width=50)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_output_btn = tk.Button(output_row, text="Browse", command=self.browse_output_dir)
        browse_output_btn.pack(side=tk.RIGHT)

        # Split button
        split_btn = tk.Button(main_frame, text="Split PDF", command=self.split_pdf,
                             bg="#4CAF50", fg="white", font=("Arial", 12, "bold"),
                             height=2, width=20)
        split_btn.pack(pady=30)

        # Status text area
        status_frame = tk.Frame(main_frame)
        status_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        tk.Label(status_frame, text="Status:", font=("Arial", 10)).pack(anchor=tk.W)

        self.status_text = tk.Text(status_frame, height=10, wrap=tk.WORD)
        scrollbar = tk.Scrollbar(status_frame, orient=tk.VERTICAL, command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=scrollbar.set)

        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Set default output directory to input PDF directory
        self.output_dir.set(os.path.dirname(os.path.abspath(__file__)))

    def browse_input_pdf(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("PDF files", "*.pdf")]
        )
        if file_path:
            self.input_pdf_path.set(file_path)
            # Set output directory to the same as input PDF by default
            self.output_dir.set(os.path.dirname(file_path))

    def browse_output_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir.set(dir_path)

    def log_status(self, message):
        self.status_text.insert(tk.END, message + "\n")
        self.status_text.see(tk.END)
        self.root.update()

    def split_pdf(self):
        input_path = self.input_pdf_path.get()
        output_directory = self.output_dir.get()

        # Validation
        if not input_path:
            messagebox.showerror("Error", "Please select an input PDF file.")
            return

        if not os.path.exists(input_path):
            messagebox.showerror("Error", "Input PDF file does not exist.")
            return

        if not output_directory:
            messagebox.showerror("Error", "Please select an output directory.")
            return

        if not os.path.exists(output_directory):
            messagebox.showerror("Error", "Output directory does not exist.")
            return

        # Generate output filenames
        input_filename = os.path.basename(input_path)
        filename_without_ext = os.path.splitext(input_filename)[0]

        colored_output_path = os.path.join(output_directory, f"{filename_without_ext}_colored.pdf")
        bw_output_path = os.path.join(output_directory, f"{filename_without_ext}_bw.pdf")

        # Disable the split button during processing
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, tk.Button) and child.cget("text") == "Split PDF":
                        child.config(state=tk.DISABLED)

        try:
            self.log_status("Starting PDF splitting process...")
            self.log_status(f"Input PDF: {input_path}")
            self.log_status(f"Colored pages output: {colored_output_path}")
            self.log_status(f"Black & White pages output: {bw_output_path}")

            # Perform the splitting
            colored_pages, bw_pages = split_pdf_by_colors(input_path, colored_output_path, bw_output_path)

            # Report results
            self.log_status("\n--- Splitting Completed ---")
            self.log_status(f"Colored pages: {len(colored_pages)} pages (pages {colored_pages})")
            self.log_status(f"Black & White pages: {len(bw_pages)} pages (pages {bw_pages})")
            self.log_status("\nFiles saved successfully!")

            messagebox.showinfo("Success", "PDF splitting completed successfully!")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.log_status(error_msg)
            messagebox.showerror("Error", error_msg)

        finally:
            # Re-enable the split button
            for widget in self.root.winfo_children():
                if isinstance(widget, tk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Button) and child.cget("text") == "Split PDF":
                            child.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = PDFSplitterApp(root)
    root.mainloop()
