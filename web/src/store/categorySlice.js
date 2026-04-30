import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { fetchCategoryCounts as apiFetchCategoryCounts } from '../api/classification';

const ZERO_SLOT = { unread: 0, total: 0 };

export const fetchCategoryCounts = createAsyncThunk(
  'category/fetchCounts',
  async ({ accountId } = {}) => {
    return apiFetchCategoryCounts({ accountId });
  }
);

const categorySlice = createSlice({
  name: 'category',
  initialState: {
    counts: { all: { ...ZERO_SLOT }, people: { ...ZERO_SLOT }, bulk: { ...ZERO_SLOT } },
    status: 'idle',  // idle | loading | succeeded | failed
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchCategoryCounts.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchCategoryCounts.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.counts = action.payload;
      })
      .addCase(fetchCategoryCounts.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.error.message;
      });
  },
});

export const selectCategoryCounts = (state) => state.category.counts;
export const selectCategoryCountsStatus = (state) => state.category.status;

export default categorySlice.reducer;
