"""TradingView sektör/alt sektör adlarının kısa Türkçe karşılıkları."""

SECTOR_TR = {
    "Commercial Services": "Ticari Hizmetler",
    "Communications": "İletişim",
    "Consumer Durables": "Dayanıklı Tüketim",
    "Consumer Non-Durables": "Tüketim Ürünleri",
    "Consumer Services": "Tüketici Hizmetleri",
    "Distribution Services": "Dağıtım",
    "Electronic Technology": "Elektronik Teknoloji",
    "Energy Minerals": "Enerji Hammaddeleri",
    "Finance": "Finans",
    "Government": "Kamu",
    "Health Services": "Sağlık Hizmetleri",
    "Health Technology": "Sağlık Teknolojisi",
    "Industrial Services": "Sanayi Hizmetleri",
    "Miscellaneous": "Diğer",
    "Non-Energy Minerals": "Madencilik ve Metal",
    "Process Industries": "Proses Sanayi",
    "Producer Manufacturing": "İmalat",
    "Retail Trade": "Perakende",
    "Technology Services": "Teknoloji Hizmetleri",
    "Transportation": "Ulaştırma",
    "Utilities": "Enerji ve Altyapı",
}

INDUSTRY_TR = {
    # Finans
    "Major Banks": "Banka", "Regional Banks": "Banka",
    "Savings Banks": "Banka", "Finance/Rental/Leasing": "Finansal Kiralama",
    "Investment Banks/Brokers": "Aracı Kurum", "Investment Managers": "Portföy Yönetimi",
    "Investment Trusts/Mutual Funds": "Yatırım Ortaklığı",
    "Real Estate Investment Trusts": "GYO", "Real Estate Development": "Gayrimenkul",
    "Property/Casualty Insurance": "Sigorta", "Multi-Line Insurance": "Sigorta",
    "Life/Health Insurance": "Hayat Sigortası", "Insurance Brokers/Services": "Sigorta",
    "Specialty Insurance": "Sigorta", "Financial Conglomerates": "Holding",
    "Financial Publishing/Services": "Finansal Hizmetler",
    # Holding
    "Industrial Conglomerates": "Holding",
    # Ulaştırma
    "Airlines": "Havacılık", "Air Freight/Couriers": "Kargo",
    "Marine Shipping": "Denizcilik", "Trucking": "Kara Taşımacılığı",
    "Railroads": "Demiryolu", "Other Transportation": "Ulaştırma",
    # Madencilik / metal / malzeme
    "Construction Materials": "Çimento ve Yapı Malz.", "Steel": "Demir Çelik",
    "Aluminum": "Alüminyum", "Other Metals/Minerals": "Metal ve Maden",
    "Precious Metals": "Altın ve Kıymetli Maden", "Forest Products": "Orman Ürünleri",
    "Coal": "Kömür",
    # Enerji
    "Electric Utilities": "Elektrik", "Gas Distributors": "Doğalgaz",
    "Alternative Power Generation": "Yenilenebilir Enerji", "Water Utilities": "Su",
    "Oil Refining/Marketing": "Rafineri", "Integrated Oil": "Petrol",
    "Oil & Gas Production": "Petrol ve Gaz", "Oil & Gas Pipelines": "Boru Hattı",
    "Contract Drilling": "Sondaj", "Oilfield Services/Equipment": "Petrol Hizmetleri",
    # Proses sanayi
    "Chemicals: Major Diversified": "Kimya", "Chemicals: Specialty": "Kimya",
    "Chemicals: Agricultural": "Gübre ve Tarım Kimyası", "Agricultural Commodities/Milling": "Tarım Ürünleri",
    "Textiles": "Tekstil", "Pulp & Paper": "Kağıt", "Containers/Packaging": "Ambalaj",
    "Industrial Specialties": "Endüstriyel Ürünler",
    # İmalat
    "Auto Parts: OEM": "Otomotiv Yan Sanayi", "Motor Vehicles": "Otomotiv",
    "Trucks/Construction/Farm Machinery": "İş Makinesi ve Ticari Araç",
    "Industrial Machinery": "Makine", "Electrical Products": "Elektrikli Ürünler",
    "Building Products": "Yapı Ürünleri", "Metal Fabrication": "Metal İşleme",
    "Miscellaneous Manufacturing": "İmalat", "Office Equipment/Supplies": "Ofis Ürünleri",
    "Aerospace & Defense": "Savunma", "Tools & Hardware": "El Aletleri",
    # Tüketim
    "Food: Major Diversified": "Gıda", "Food: Specialty/Candy": "Gıda",
    "Food: Meat/Fish/Dairy": "Gıda", "Beverages: Non-Alcoholic": "İçecek",
    "Beverages: Alcoholic": "İçecek", "Tobacco": "Tütün",
    "Household/Personal Care": "Kişisel Bakım", "Apparel/Footwear": "Hazır Giyim",
    "Home Furnishings": "Mobilya ve Ev", "Electronics/Appliances": "Beyaz Eşya ve Elektronik",
    "Automotive Aftermarket": "Otomotiv Yedek Parça", "Recreational Products": "Eğlence Ürünleri",
    "Homebuilding": "Konut İnşaatı", "Consumer Sundries": "Tüketim Ürünleri",
    # Perakende
    "Food Retail": "Gıda Perakende", "Department Stores": "Mağazacılık",
    "Discount Stores": "İndirim Marketi", "Specialty Stores": "Perakende",
    "Apparel/Footwear Retail": "Giyim Perakende", "Electronics/Appliance Stores": "Elektronik Perakende",
    "Home Improvement Chains": "Yapı Market", "Drugstore Chains": "Eczane Zinciri",
    "Internet Retail": "E-Ticaret", "Catalog/Specialty Distribution": "Dağıtım",
    # Hizmetler
    "Hotels/Resorts/Cruise lines": "Turizm", "Restaurants": "Restoran",
    "Casinos/Gaming": "Şans Oyunları", "Movies/Entertainment": "Medya ve Eğlence",
    "Broadcasting": "Yayıncılık", "Publishing: Newspapers": "Yayıncılık",
    "Publishing: Books/Magazines": "Yayıncılık", "Cable/Satellite TV": "Yayıncılık",
    "Other Consumer Services": "Hizmet", "Advertising/Marketing Services": "Reklam",
    "Engineering & Construction": "İnşaat ve Taahhüt", "Environmental Services": "Çevre Hizmetleri",
    "Miscellaneous Commercial Services": "Ticari Hizmetler", "Personnel Services": "İK Hizmetleri",
    "Commercial Printing/Forms": "Matbaa",
    # İletişim / teknoloji
    "Major Telecommunications": "Telekom", "Wireless Telecommunications": "Telekom",
    "Specialty Telecommunications": "Telekom", "Telecommunications Equipment": "Telekom Ekipmanı",
    "Packaged Software": "Yazılım", "Information Technology Services": "Bilişim",
    "Internet Software/Services": "İnternet", "Data Processing Services": "Bilişim",
    "Computer Processing Hardware": "Donanım", "Computer Peripherals": "Donanım",
    "Electronic Components": "Elektronik", "Electronic Equipment/Instruments": "Elektronik",
    "Electronic Production Equipment": "Elektronik", "Semiconductors": "Yarı İletken",
    # Sağlık
    "Pharmaceuticals: Major": "İlaç", "Pharmaceuticals: Other": "İlaç",
    "Pharmaceuticals: Generic": "İlaç", "Medical Specialties": "Tıbbi Cihaz",
    "Hospital/Nursing Management": "Hastane", "Medical/Nursing Services": "Sağlık Hizmetleri",
    "Medical Distributors": "Medikal Dağıtım", "Biotechnology": "Biyoteknoloji",
    # Dağıtım
    "Wholesale Distributors": "Toptan Ticaret", "Food Distributors": "Gıda Dağıtım",
    "Electronics Distributors": "Elektronik Dağıtım",
    "Computer Communications": "Bilişim", "Media Conglomerates": "Medya ve Eğlence",
    "Miscellaneous": "Diğer", "Other Consumer Specialties": "Tüketim Ürünleri",
}

# Kaynağın yanlış ya da çok geniş sınıflandırdığı bilinen şirketler (elle düzeltme)
OVERRIDES = {
    "KCHOL": ("Holding", "Holding"), "SAHOL": ("Holding", "Holding"),
    "DOHOL": ("Holding", "Holding"), "AGHOL": ("Holding", "Holding"),
    "ALARK": ("Holding", "Holding"), "TKFEN": ("Holding", "Holding"),
    "GSDHO": ("Holding", "Holding"), "NTHOL": ("Holding", "Holding"),
    "GLYHO": ("Holding", "Holding"), "ECZYT": ("Holding", "Holding"),
    "BERA": ("Holding", "Holding"), "POLHO": ("Holding", "Holding"),
    "SISE": ("Cam", "Proses Sanayi"), "TRKCM": ("Cam", "Proses Sanayi"),
    # kaynakta sektörü boş gelenler
    "ISATR": ("Banka", "Finans"), "ISBTR": ("Banka", "Finans"), "ISCTR": ("Banka", "Finans"),
    "EKGYO": ("GYO", "Finans"), "KRDMB": ("Demir Çelik", "Madencilik ve Metal"),
    "KRDMD": ("Demir Çelik", "Madencilik ve Metal"), "AVTUR": ("Turizm", "Tüketici Hizmetleri"),
    "ISGSY": ("Girişim Sermayesi", "Finans"), "VERTU": ("Girişim Sermayesi", "Finans"),
}


def tr_label(sector: str | None, industry: str | None) -> tuple[str | None, str | None]:
    """(kısa etiket, ana sektör) döndürür."""
    main = SECTOR_TR.get(sector or "", sector or None)
    label = INDUSTRY_TR.get(industry or "") or main
    return label, main
