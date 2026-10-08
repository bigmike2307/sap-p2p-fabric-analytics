@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: invoice accounting header'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #XL, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_BKPF
  as select from bkpf
{
  key bukrs,
  key belnr,
  key gjahr,
      blart,
      bldat,
      budat,
      awtyp,
      awkey, // = RBKP-BELNR + RBKP-GJAHR: links the FI document to the supplier invoice
      xblnr,
      waers,
      usnam
}
where
  awtyp = 'RMRP' // documents posted by logistics invoice verification (MIRO)
