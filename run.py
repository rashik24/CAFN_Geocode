import io
import time

import pandas as pd
import requests
import streamlit as st


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Agency Geocoder",
    page_icon="📍",
    layout="wide",
)


# ============================================================
# CONFIG
# ============================================================
MAPBOX_URL = "https://api.mapbox.com/search/geocode/v6/forward"


# ============================================================
# HELPER FUNCTIONS
# ============================================================
def read_uploaded_file(uploaded_file):
    extension = uploaded_file.name.lower().split(".")[-1]

    if extension == "csv":
        return pd.read_csv(uploaded_file)

    if extension in ["xlsx", "xls"]:
        return pd.read_excel(uploaded_file)

    raise ValueError("Please upload a CSV, XLSX, or XLS file.")


def clean_address(address):
    if pd.isna(address):
        return ""

    return " ".join(str(address).strip().split())


def geocode_address(address, mapbox_token, country="US"):
    address = clean_address(address)

    if not address:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "MISSING_ADDRESS",
            "Geocode Error": None,
        }

    params = {
        "q": address,
        "access_token": mapbox_token,
        "limit": 1,
        "autocomplete": "false",
    }

    if country.strip():
        params["country"] = country.strip().upper()

    try:
        response = requests.get(
            MAPBOX_URL,
            params=params,
            timeout=30,
        )

        data = response.json()

        if response.status_code != 200:
            return {
                "Latitude": None,
                "Longitude": None,
                "Matched Address": None,
                "Geocode Status": f"HTTP_{response.status_code}",
                "Geocode Error": data.get(
                    "message",
                    response.text,
                ),
            }

        features = data.get("features", [])

        if not features:
            return {
                "Latitude": None,
                "Longitude": None,
                "Matched Address": None,
                "Geocode Status": "ZERO_RESULTS",
                "Geocode Error": None,
            }

        first_result = features[0]

        geometry = first_result.get("geometry", {})
        coordinates = geometry.get("coordinates", [])

        if len(coordinates) < 2:
            return {
                "Latitude": None,
                "Longitude": None,
                "Matched Address": None,
                "Geocode Status": "INVALID_COORDINATES",
                "Geocode Error": "No valid coordinates were returned.",
            }

        # GeoJSON order is longitude, latitude
        longitude = coordinates[0]
        latitude = coordinates[1]

        properties = first_result.get("properties", {})

        matched_address = (
            properties.get("full_address")
            or properties.get("name")
            or first_result.get("place_name")
        )

        return {
            "Latitude": latitude,
            "Longitude": longitude,
            "Matched Address": matched_address,
            "Geocode Status": "OK",
            "Geocode Error": None,
        }

    except requests.exceptions.Timeout:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "TIMEOUT",
            "Geocode Error": "The Mapbox request timed out.",
        }

    except requests.exceptions.RequestException as error:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "REQUEST_FAILED",
            "Geocode Error": str(error),
        }

    except Exception as error:
        return {
            "Latitude": None,
            "Longitude": None,
            "Matched Address": None,
            "Geocode Status": "UNKNOWN_ERROR",
            "Geocode Error": str(error),
        }


def dataframe_to_excel(df):
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Geocoded Agencies",
        )

    output.seek(0)
    return output.getvalue()


# ============================================================
# APP HEADER
# ============================================================
st.title("📍 Agency Address Geocoder")

st.write(
    "Upload an Excel or CSV file containing agency addresses. "
    "The app will use Mapbox to generate latitude and longitude."
)


# ============================================================
# SIDEBAR SETTINGS
# ============================================================
with st.sidebar:
    st.header("Geocoding Settings")

    mapbox_token = st.secrets["MAPBOX_TOKEN"]

    country = st.text_input(
        "Country code",
        value="US",
        help="Use US for United States addresses.",
    )

    request_delay = st.number_input(
        "Delay between requests",
        min_value=0.0,
        max_value=5.0,
        value=0.1,
        step=0.1,
        help="Pause between Mapbox requests.",
    )


# ============================================================
# FILE UPLOAD
# ============================================================
uploaded_file = st.file_uploader(
    "Upload agency file",
    type=["xlsx", "xls", "csv"],
)

if uploaded_file is None:
    st.info("Upload an Excel or CSV file to begin.")
    st.stop()


# ============================================================
# READ FILE
# ============================================================
try:
    df = read_uploaded_file(uploaded_file)

except Exception as error:
    st.error(f"Could not read the file: {error}")
    st.stop()


if df.empty:
    st.warning("The uploaded file contains no rows.")
    st.stop()


# ============================================================
# DATA PREVIEW
# ============================================================
st.subheader("Uploaded data")

st.write(f"Number of rows: **{len(df):,}**")

st.dataframe(
    df.head(25),
    use_container_width=True,
)


# ============================================================
# SELECT ADDRESS COLUMN
# ============================================================
default_address_index = 0

for index, column in enumerate(df.columns):
    if str(column).strip().lower() == "address":
        default_address_index = index
        break


address_column = st.selectbox(
    "Select the address column",
    options=list(df.columns),
    index=default_address_index,
)


skip_existing = st.checkbox(
    "Skip rows that already have Latitude and Longitude",
    value=True,
)


# ============================================================
# GEOCODE BUTTON
# ============================================================
run_geocoding = st.button(
    "Geocode agencies",
    type="primary",
    use_container_width=True,
)


# ============================================================
# RUN GEOCODING
# ============================================================
if run_geocoding:
    if not mapbox_token.strip():
        st.error("Enter your Mapbox access token.")
        st.stop()

    result_df = df.copy()

    output_columns = [
        "Latitude",
        "Longitude",
        "Matched Address",
        "Geocode Status",
        "Geocode Error",
    ]

    for column in output_columns:
        if column not in result_df.columns:
            result_df[column] = None

    progress_bar = st.progress(0)
    status_message = st.empty()

    total_rows = len(result_df)

    for row_number, (row_index, row) in enumerate(
        result_df.iterrows(),
        start=1,
    ):
        address = clean_address(row[address_column])

        existing_latitude = pd.to_numeric(
            pd.Series([row.get("Latitude")]),
            errors="coerce",
        ).iloc[0]

        existing_longitude = pd.to_numeric(
            pd.Series([row.get("Longitude")]),
            errors="coerce",
        ).iloc[0]

        has_existing_coordinates = (
            pd.notna(existing_latitude)
            and pd.notna(existing_longitude)
        )

        if skip_existing and has_existing_coordinates:
            result_df.at[
                row_index,
                "Geocode Status",
            ] = "EXISTING_COORDINATES"

        else:
            status_message.write(
                f"Geocoding {row_number:,} of "
                f"{total_rows:,}: {address}"
            )

            geocode_result = geocode_address(
                address=address,
                mapbox_token=mapbox_token.strip(),
                country=country,
            )

            for column, value in geocode_result.items():
                result_df.at[row_index, column] = value

            if request_delay > 0 and row_number < total_rows:
                time.sleep(request_delay)

        progress_bar.progress(row_number / total_rows)

    progress_bar.empty()
    status_message.empty()

    result_df["Latitude"] = pd.to_numeric(
        result_df["Latitude"],
        errors="coerce",
    )

    result_df["Longitude"] = pd.to_numeric(
        result_df["Longitude"],
        errors="coerce",
    )

    st.session_state["geocoded_results"] = result_df


# ============================================================
# DISPLAY RESULTS
# ============================================================
if "geocoded_results" in st.session_state:
    result_df = st.session_state["geocoded_results"]

    valid_coordinates = (
        result_df["Latitude"].notna()
        & result_df["Longitude"].notna()
    )

    matched_count = int(valid_coordinates.sum())
    unmatched_count = int((~valid_coordinates).sum())

    st.subheader("Geocoding summary")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Total agencies",
        f"{len(result_df):,}",
    )

    col2.metric(
        "Successfully geocoded",
        f"{matched_count:,}",
    )

    col3.metric(
        "Not geocoded",
        f"{unmatched_count:,}",
    )


    # ========================================================
    # RESULTS TABLE
    # ========================================================
    st.subheader("Results")

    st.dataframe(
        result_df,
        use_container_width=True,
    )


    # ========================================================
    # MAP
    # ========================================================
    if matched_count > 0:
        st.subheader("Agency map")

        map_df = result_df.loc[
            valid_coordinates,
            ["Latitude", "Longitude"],
        ].copy()

        map_df = map_df.rename(
            columns={
                "Latitude": "latitude",
                "Longitude": "longitude",
            }
        )

        st.map(map_df)


    # ========================================================
    # UNMATCHED ROWS
    # ========================================================
    if unmatched_count > 0:
        st.subheader("Addresses requiring review")

        review_columns = [
            address_column,
            "Geocode Status",
            "Geocode Error",
        ]

        if "Matched Address" in result_df.columns:
            review_columns.append("Matched Address")

        st.dataframe(
            result_df.loc[
                ~valid_coordinates,
                review_columns,
            ],
            use_container_width=True,
        )


    # ========================================================
    # DOWNLOAD EXCEL
    # ========================================================
    excel_output = dataframe_to_excel(result_df)

    st.download_button(
        label="Download geocoded Excel file",
        data=excel_output,
        file_name="Geocoded_Agencies.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        type="primary",
        use_container_width=True,
    )
