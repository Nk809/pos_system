def scan_barcode():
    try:
        import cv2
        from pyzbar.pyzbar import decode
    except Exception as exc:
        raise RuntimeError(
            "Barcode dependencies are missing. Install opencv-python and pyzbar."
        ) from exc

    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        cam.release()
        raise RuntimeError("Unable to access camera.")

    try:
        while True:
            ret, frame = cam.read()
            if not ret or frame is None:
                continue

            for code in decode(frame):
                data = code.data.decode("utf-8")
                return data

            cv2.imshow("Scan Barcode (Press ESC to cancel)", frame)
            if cv2.waitKey(1) == 27:
                return None
    finally:
        cam.release()
        cv2.destroyAllWindows()
