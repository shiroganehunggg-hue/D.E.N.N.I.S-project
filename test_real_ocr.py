from PIL import ImageGrab
import pytesseract
import time


def main():
    pytesseract.pytesseract.tesseract_cmd = (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    print("Bạn có 5 giây để mở một màn hình có chữ rõ ràng...")
    time.sleep(5)

    image = ImageGrab.grab()
    image.save("ocr_test.png")

    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT
    )

    print("\n=== OCR RESULTS ===\n")

    for i, raw_text in enumerate(data["text"]):
        text = raw_text.strip()

        if not text:
            continue

        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            continue

        if conf < 0:
            continue

        print({
            "text": text,
            "x": data["left"][i],
            "y": data["top"][i],
            "width": data["width"][i],
            "height": data["height"][i],
            "confidence": round(conf / 100, 3)
        })


if __name__ == "__main__":
    main()