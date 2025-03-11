import streamlit as st
import pandas as pd
from streamlit_option_menu import option_menu
import datetime
from io import StringIO, BytesIO
import boto3

AWS_ACCESS_KEY_ID = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
S3_BUCKET_NAME = st.secrets["S3_BUCKET_NAME"]
S3_REGION = st.secrets["S3_REGION"]
DATA_FILE = st.secrets["DATA_FILE"]

st.set_page_config(
    page_title='Manajemen Misdinar Gereja Santo Marinus',
    page_icon=":church:"
)

s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=S3_REGION
)

# Load Data from Local File
def load_data():
    obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=DATA_FILE)
    df = pd.read_csv(StringIO(obj["Body"].read().decode("utf-8")), dtype={'ID':'str','Partisipasi':'int'})

    return df

df = load_data()

def delete_old_rosters():
    today = datetime.date.today()

    # List objects in the "rosters/" folder in S3
    response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix="rosters/")
    
    if "Contents" in response:
        for obj in response["Contents"]:
            file_key = obj["Key"]  # Full S3 path (e.g., "rosters/misdinar_SabtuSore_8 Maret 2025.csv")
            file_name = file_key.split("/")[-1]  # Extract filename
           
            if file_name.startswith("misdinar_") and file_name.endswith(".csv"):
                try:
                    # Extract date from filename
                    date_str = file_name.split("_")[-1].replace(".csv", "")  # e.g., "8 Maret 2025"
                    roster_date = datetime.datetime.strptime(date_str, "%A, %d %B %Y").date()
                    
                    # Delete if the date is in the past
                    if roster_date < today:
                        s3.delete_object(Bucket=S3_BUCKET_NAME, Key=file_key)
                        print(f"Deleted old roster from S3: {file_key}")

                except Exception as e:
                    print(f"Skipping {file_name}: {e}")

# Call function at startup to remove outdated roster files
delete_old_rosters()

# Streamlit App Title
st.title("Manajemen Jadwal Misdinar Santo Marinus Karawang")

# Main Menu
with st.sidebar:
    menu = option_menu(
        menu_title=None,
        options= ["Buat Jadwal Misdinar", "Ubah Jadwal Misdinar", "Update Data Misdinar"],
        icons= ["calendar-plus", "journal-bookmark", "database-fill-gear"],
        menu_icon="cast",
        default_index=0
    )

if menu == "Buat Jadwal Misdinar":
    st.header("Buat Jadwal Misdinar")
    
    misa_options = {
        "Jumat Pertama": 4,
        "Sabtu Sore": 6,
        "Minggu Pagi Pertama": 11,
        "Minggu Sore Pertama": 11,
        "Minggu Pagi Biasa": 8,
        "Minggu Sore Biasa": 8,
        "Jalan Salib": 3,
        "Hari Raya": 11
    }
    selected_misa = st.selectbox("Pilih Kategori Misa:", list(misa_options.keys()))
    required_count = misa_options[selected_misa]

    # User input for roster date
    roster_date = st.date_input("Pilih Tanggal Misa:", format='DD/MM/YYYY')
    formatted_date = roster_date.strftime("%A, %d %B %Y")
    
    lingkungan_options = df["Lingkungan"].unique().tolist()
    lingkungan_options.append('Lainnya')
    selected_lingkungan = st.selectbox("Pilih Petugas Koor:", lingkungan_options)
    
    st.write(f"Kategori Misa: {selected_misa}, butuh {required_count} petugas Misdinar")
    st.write(f"Tanggal Misa: {formatted_date}")
    st.write(f"Petugas Koor: {selected_lingkungan}")
    
    # Filter altar servers based on the selection criteria
    df_misdinar = df[df["Peran"] == "Misdinar"].copy()
    df_misdinar["Partisipasi"] = df_misdinar["Partisipasi"].fillna(0)
    
    # Priority 1: Same Lingkungan as choir duty
    if selected_lingkungan != 'Lainnya':
        priority_1 = df_misdinar[df_misdinar["Lingkungan"] == selected_lingkungan]
    else:
        priority_1 = df_misdinar
    
    # Priority 2: Least participation
    priority_1 = priority_1.sort_values(by="Partisipasi").head(required_count)
    priority_1_non = priority_1[priority_1['Notes'].isnull()]
    priority_1_sps = priority_1[priority_1['Notes'].notnull()]
    special_needed = max(1, required_count // 4)

    if len(priority_1_non) < required_count:
        priority_1_sps = priority_1_sps.head(special_needed)
        priority_1 = pd.concat([priority_1_non, priority_1_sps], ignore_index=True)
    else:
        priority_1 = priority_1_non
    
    if len(priority_1) < required_count:
        remaining_spots = required_count - len(priority_1)
        special_count = len(priority_1[priority_1['Notes'].notnull()])
        if special_count >= special_needed:
            filler = df_misdinar[(~df_misdinar["ID"].isin(priority_1['ID'])) & (df_misdinar['Notes'].isnull())]
            filler = filler.sort_values(by='Partisipasi').head(remaining_spots)
        else:
            special_needed = special_needed - special_count
            special = df_misdinar[(~df_misdinar["ID"].isin(priority_1['ID'])) & (~df_misdinar['Notes'].isnull())].head(special_needed)
            filler = df_misdinar[(~df_misdinar["ID"].isin(priority_1['ID'])) & (~df_misdinar['ID'].isin(special['ID']))  & (df_misdinar['Notes'].isnull())].head(remaining_spots - special_needed)
            filler = pd.concat([filler, special])

        selected_roster = pd.concat([priority_1, filler])
    else:
        selected_roster = priority_1
    
    # Select one Organist
    df_organist = df[df["Peran"] == "Organis"].copy()
    df_organist["Partisipasi"] = df_organist["Partisipasi"].fillna(0)
    organist_priority = df_organist[df_organist["Lingkungan"] == selected_lingkungan].sort_values(by="Partisipasi")
    if organist_priority.empty:
        organist_priority = df_organist.sort_values(by="Partisipasi")
    selected_organist = organist_priority.head(1)
    
    # Combine roster
    full_roster = pd.concat([selected_roster, selected_organist])
    
    st.write("### Petugas Misdinar:")
    st.dataframe(full_roster[["Nama", "Lingkungan", "Peran", "Notes"]], width=1000, hide_index=True)

    # Confirmation Button
    if st.button("Konfirmasi", type='primary'):
        roster_text = f"Jadwal Misdinar - {selected_misa}\n{formatted_date}\n\nNama - Lingkungan\n"
        roster_text += "\n".join([f"{row['Nama']} - {row['Lingkungan']}" for _, row in full_roster.iterrows()])
        
        #Update Partisipasi column
        df.loc[df['ID'].isin(full_roster['ID']), 'Partisipasi'] += 1

        #Save updated data.csv back to S3
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        s3.put_object(Bucket=S3_BUCKET_NAME, Key="data.csv", Body=csv_buffer.getvalue())

        # Generate roster filename (e.g., "misdinar_SabtuSore_2025-03-08.csv")
        roster_filename = f"misdinar_{selected_misa}_{formatted_date}.csv"

        # Convert DataFrame to CSV for S3 upload
        roster_buffer = StringIO()
        full_roster.to_csv(roster_buffer, index=False)

        # Upload roster file to S3
        s3.put_object(Bucket=S3_BUCKET_NAME, Key=f"rosters/{roster_filename}", Body=roster_buffer.getvalue())

        # Display formatted text output
        st.code(roster_text, height=200, language='python')

        st.success(f"Jadwal Misdinar berhasil dibuat!")

elif menu == "Ubah Jadwal Misdinar":
    st.header("Ubah Jadwal Misdinar")
    
    # List roster files from S3
    response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix="rosters/")
    roster_files = [obj["Key"] for obj in response.get("Contents", []) if obj["Key"].endswith(".csv")]
    
    if roster_files:
        # Format file names for display
        display_roster_files = {f: f.replace("rosters/misdinar_", "").replace(".csv", "").replace("_", " - ") for f in roster_files}
        
        selected_roster_file = st.selectbox("Pilih Jadwal Tugas Misdinar:", list(display_roster_files.values()))
        actual_file_key = [key for key, value in display_roster_files.items() if value == selected_roster_file][0]
        
        # Download the selected roster from S3
        obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=actual_file_key)
        roster_df = pd.read_csv(BytesIO(obj["Body"].read()), dtype={'ID':'str','Partisipasi':'int'})
        
        st.write("### Petugas Misdinar")
        st.dataframe(roster_df[["ID","Nama", "Lingkungan", "Peran", "Notes"]], width=1000, hide_index=True)
        
        # Select a person to replace
        selected_person = st.selectbox(
            "Pilih petugas misdinar yang ingin diganti:",
            roster_df.apply(lambda row: f"{row['ID']}. {row['Nama']} - {row['Lingkungan']} - {row['Peran']}", axis=1).tolist()
        )
        
        available_replacements = df[
            df["Peran"].isin(["Misdinar", "Organis"]) & ~df["Nama"].isin(roster_df["Nama"])
        ].sort_values(by=['Peran', 'Lingkungan', 'Nama'])
        
        replacement_person = st.selectbox(
            "Pilih pengganti petugas misdinar:",
            available_replacements.apply(lambda row: f"{row['ID']}. {row['Nama']} - {row['Lingkungan']} - {row['Peran']}", axis=1).tolist()
        )
        
        if st.button("Konfirmasi", type='primary'):
            # Update the roster
            roster_df = pd.concat([roster_df, df.loc[df['ID']==replacement_person.split(". ")[0]]], ignore_index=True).drop(roster_df.loc[roster_df["ID"] == selected_person.split(". ")[0]].index)
            
            # Save back to S3
            roster_buffer = StringIO()
            roster_df.to_csv(roster_buffer, index=False)
            s3.put_object(Bucket=S3_BUCKET_NAME, Key=actual_file_key, Body=roster_buffer.getvalue())

            # Update partisipasi petugas
            df.loc[df['ID']==replacement_person.split(". ")[0], 'Partisipasi'] +=1
            df.loc[df["ID"] == selected_person.split(". ")[0], 'Partisipasi'] -=1

            # Save updated data to S3
            csv_buffer = StringIO()
            df.to_csv(csv_buffer, index=False)
            s3.put_object(Bucket=S3_BUCKET_NAME, Key=DATA_FILE, Body=csv_buffer.getvalue())
            st.rerun()
            
            st.success("Perubahan Jadwal Petugas Misdinar Berhasil!")
    
    else:
        st.write("Belum ada jadwal tugas misdinar yang dibuat.")

elif menu == "Update Data Misdinar":
    st.header("Update Data Misdinar")

    lingkungan_options = df["Lingkungan"].unique().tolist()
    peran_options = df["Peran"].unique().tolist()

    with st.expander('Tambah Data Misdinar'):
        new_data = {}
        for col in df.columns:
            if col == "ID":
                new_data[col] = '0'
            elif col == "Partisipasi":
                new_data[col] = 0
            elif col == "Peran":
                new_data[col] = st.selectbox("Pilih Peran Petugas:", list(peran_options))
            elif col == "Lingkungan":
                new_data[col] = st.selectbox("Pilih Asal Lingkungan Petugas:", list(lingkungan_options))
            else:
                new_data[col] = st.text_input(col, "")
        if st.button("Tambah Data Petugas",type='primary'):
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            df = df.drop(columns='ID')
            df = df.sort_values(by=['Lingkungan', 'Nama', 'Peran'])
            df = df.reset_index().rename(columns={'index':'ID'})

            csv_buffer = StringIO()
            df.to_csv(csv_buffer, index=False)
            s3.put_object(Bucket=S3_BUCKET_NAME, Key=DATA_FILE, Body=csv_buffer.getvalue())

            st.success("Data petugas misdinar berhasil ditambahkan!")
    
    with st.expander('Hapus Data Misdinar'):
        st.dataframe(df, width=1000)
        selected_remove = st.selectbox("Pilih petugas misdinar yang ingin dihapus", df.apply(lambda row: f"{row['ID']}. {row['Nama']} - {row['Lingkungan']} - {row['Peran']}", axis=1).tolist())
        if st.button("Hapus Data Petugas", type='primary'):
            df = df[df["ID"] != selected_remove.split(". ")[0]]
            df = df.drop(columns='ID')
            df = df.sort_values(by=['Peran','Lingkungan', 'Nama'])
            df = df.reset_index().rename(columns={'index':'ID'})

            csv_buffer = StringIO()
            df.to_csv(csv_buffer, index=False)
            s3.put_object(Bucket=S3_BUCKET_NAME, Key=DATA_FILE, Body=csv_buffer.getvalue())

            st.success("Data petugas misdinar berhasil dihapus!")
    
    with st.expander('Upload Data Baru'):
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            st.warning('Pastikan Data yang diupload sudah benar!')
            if st.button('Konfirmasi',type='primary'):
                csv_buffer = StringIO()
                df.to_csv(csv_buffer, index=False)
                s3.put_object(Bucket=S3_BUCKET_NAME, Key=DATA_FILE, Body=csv_buffer.getvalue())

                st.success("Data berhasil diperbarui!")